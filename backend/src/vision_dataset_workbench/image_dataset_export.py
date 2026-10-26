"""Freeze image samples and assign exact-content groups to one export split."""

import math
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from .image_import import fingerprint
from .models import ImageAsset, ImageDirectory, ImageImport, ProjectLabel
from .services.images import ImageService, ImageConflict


def target_train_count(count, ratio):
    if count < 0 or not math.isfinite(ratio) or not 0 <= ratio <= 1:
        raise ValueError("图片数或训练比例无效")
    target = math.floor(count * ratio + 0.5)
    return min(count - 1, max(1, target)) if count >= 2 and 0 < ratio < 1 else target


def export_names(samples, directories):
    used = set()
    names = {}
    for sample in samples:
        directory = directories[sample["directory_id"]]
        relative = Path(sample["source_relative_path"])
        # Reserve enough bytes for the suffix, extension and matching TXT filename.
        stem = (directory["name"] + "_" + relative.stem).replace("/", "_").replace("\\", "_")
        stem = (
            "".join(c if c.isalnum() or c in " -_." else "_" for c in stem).strip(" .") or "image"
        )
        stem = stem.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(" .")
        name, number = stem, 2
        while name.casefold() in used:
            name, number = f"{stem}_{number}", number + 1
        used.add(name.casefold())
        names[sample["image_id"]] = name + relative.suffix.lower()
    return names


def freeze_images(db, workspace, project_id, labels, rules, train_ratio, seed):
    directories = list(
        db.scalars(
            select(ImageDirectory)
            .join(ImageImport)
            .where(ImageDirectory.project_id == project_id, ImageImport.status == "ready")
            .order_by(ImageDirectory.sort_order, ImageDirectory.id)
        )
    )
    by_directory = {
        d.id: {
            "directory_id": d.id,
            "name": d.name,
            "import_id": d.import_id,
            "source_relative_path": d.source_relative_path,
        }
        for d in directories
    }
    if (
        rules is None
        or len(rules) != len(directories)
        or {r["directory_id"] for r in rules} != set(by_directory)
    ):
        raise ValueError("目录规则必须恰好覆盖当前所有目录")
    by_rule = {r["directory_id"]: r for r in rules}
    for rule in rules:
        mode, ratio = rule["mode"], rule.get("train_ratio")
        if mode not in {"train", "val", "ratio"} or (mode != "ratio" and ratio is not None):
            raise ValueError("目录划分规则无效")
        target_train_count(0, train_ratio if ratio is None else ratio)
    if not any(r["included"] for r in rules):
        raise ValueError("至少选择一个参与目录")
    images = list(
        db.scalars(
            ImageService.query(project_id).order_by(
                ImageDirectory.sort_order,
                ImageDirectory.id,
                ImageAsset.source_relative_path,
                ImageAsset.id,
            )
        )
    )
    annotations = defaultdict(list)
    for a in ImageService.annotations(db, [i.id for i in images]):
        annotations[a.image_id].append(a)
    enabled_labels = {label["source_label_id"] for label in labels if label["enabled"]}
    stats = {
        d.id: {
            **by_directory[d.id],
            "total_images": 0,
            "effective_images": 0,
            "excluded": {},
            "train_images": 0,
            "val_images": 0,
            "positive_images": 0,
            "negative_images": 0,
            "train_positive_images": 0,
            "val_positive_images": 0,
            "train_negative_images": 0,
            "val_negative_images": 0,
            "rule": by_rule[d.id],
        }
        for d in directories
    }
    groups = defaultdict(list)
    excluded = Counter()
    revisions = []
    for image in images:
        stat = stats[image.directory_id]
        stat["total_images"] += 1
        revisions.append(
            [
                image.id,
                image.version,
                image.annotation_revision,
                image.annotation_status,
                image.enabled,
                image.content_sha256,
            ]
        )
        rule = by_rule[image.directory_id]
        reason = (
            "directory_excluded"
            if not rule["included"]
            else "disabled"
            if not image.enabled
            else None
        )
        if reason is None:
            path = workspace / image.file_path
            root = workspace / "projects" / project_id / "images"
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(root.resolve())
                or not path.is_file()
            ):
                reason = "file_unavailable"
        if reason:
            excluded[reason] += 1
            stat["excluded"][reason] = stat["excluded"].get(reason, 0) + 1
            continue
        groups[image.content_sha256].append(image)
    candidates = []
    for digest, members in sorted(groups.items()):
        signatures = {
            fingerprint(
                sorted(
                    [[a.label_id, a.x_min, a.y_min, a.x_max, a.y_max] for a in annotations[i.id]]
                )
            )
            for i in members
        }
        if len(signatures) != 1:
            paths = ", ".join(
                by_directory[i.directory_id]["name"] + "/" + i.file_name for i in members
            )
            raise ImageConflict(f"完全相同图片的状态或标注不一致：{paths}")
        pins = {
            by_rule[i.directory_id]["mode"]
            for i in members
            if by_rule[i.directory_id]["mode"] != "ratio"
        }
        if len(pins) > 1:
            paths = ", ".join(by_directory[i.directory_id]["name"] for i in members)
            raise ImageConflict(f"完全相同图片被同时指定训练集和验证集：{paths}")
        candidates.append(
            {
                "hash": digest,
                "members": members,
                "pin": next(iter(pins), None),
                "counts": Counter(
                    (
                        i.directory_id,
                        "positive"
                        if any(a.label_id in enabled_labels for a in annotations[i.id])
                        else "negative",
                    )
                    for i in members
                ),
            }
        )
        for i in members:
            stats[i.directory_id]["effective_images"] += 1
            kind = (
                "positive"
                if any(a.label_id in enabled_labels for a in annotations[i.id])
                else "negative"
            )
            stats[i.directory_id][kind + "_images"] += 1
    targets = {
        (d, kind): target_train_count(
            s[kind + "_images"],
            by_rule[d].get("train_ratio")
            if by_rule[d].get("train_ratio") is not None
            else train_ratio,
        )
        for d, s in stats.items()
        if by_rule[d]["mode"] == "ratio"
        for kind in ("positive", "negative")
    }
    counts = Counter()
    sides = {}

    def cost(delta):
        coverage, deviation = 0, 0
        for key, target in targets.items():
            actual = counts[key] + delta.get(key, 0)
            total = stats[key[0]][key[1] + "_images"]
            if 0 < target < total and actual in {0, total}:
                coverage += 1
            deviation += abs(actual - target)
        return coverage, deviation

    for group in candidates:
        if group["pin"]:
            sides[group["hash"]] = group["pin"]
            if group["pin"] == "train":
                counts.update(group["counts"])
    movable = sorted(
        (g for g in candidates if not g["pin"]), key=lambda g: fingerprint([seed, g["hash"]])
    )
    for group in movable:
        train_cost, val_cost = cost(group["counts"]), cost({})
        side = (
            "train"
            if train_cost < val_cost
            or (
                train_cost == val_cost
                and int(fingerprint([seed, group["hash"], "tie"]), 16) % 2 == 0
            )
            else "val"
        )
        sides[group["hash"]] = side
        if side == "train":
            counts.update(group["counts"])
    local_groups = defaultdict(list)
    for group in movable:
        if len(group["counts"]) == 1:
            local_groups[next(iter(group["counts"]))].append(group)
    subsets = {}
    for key, groups_in_stratum in local_groups.items():
        reachable, parents = 1, {0: None}
        for group in groups_in_stratum:
            size = group["counts"][key]
            new = (reachable << size) & ~reachable
            reachable |= new
            while new:
                bit = new & -new
                total = bit.bit_length() - 1
                parents[total] = (total - size, group["hash"])
                new ^= bit
        subsets[key] = parents
    # Strictly decreasing coverage/deviation cost terminates without splitting a hash group.
    # shortcut: cross-directory groups use local improvement; use a joint solver for a global optimum.
    changed = True
    while changed:
        changed = False
        for group in movable:
            sign = -1 if sides[group["hash"]] == "train" else 1
            delta = {d: sign * n for d, n in group["counts"].items()}
            if cost(delta) < cost({}):
                counts.update(delta)
                sides[group["hash"]] = "val" if sign == -1 else "train"
                changed = True
        for key, parents in subsets.items():
            local_train = sum(
                g["counts"][key] for g in local_groups[key] if sides[g["hash"]] == "train"
            )
            best = min(parents, key=lambda n: (cost({key: n - local_train}), n))
            if cost({key: best - local_train}) < cost({}):
                counts[key] += best - local_train
                chosen = set()
                while best:
                    best, digest = parents[best]
                    chosen.add(digest)
                for group in local_groups[key]:
                    sides[group["hash"]] = "train" if group["hash"] in chosen else "val"
                changed = True
    samples = []
    filtered = 0
    for group in candidates:
        for image in group["members"]:
            side = sides[group["hash"]]
            stats[image.directory_id][side + "_images"] += 1
            kind = (
                "positive"
                if any(a.label_id in enabled_labels for a in annotations[image.id])
                else "negative"
            )
            stats[image.directory_id][side + "_" + kind + "_images"] += 1
            filtered += sum(a.label_id not in enabled_labels for a in annotations[image.id])
            samples.append(
                {
                    "image_id": image.id,
                    "directory_id": image.directory_id,
                    "source_relative_path": image.source_relative_path,
                    "file_name": image.file_name,
                    "content_sha256": image.content_sha256,
                    "width": image.width,
                    "height": image.height,
                    "annotation_revision": image.annotation_revision,
                    "version": image.version,
                    "split": side,
                    "positive": kind == "positive",
                }
            )
    samples.sort(
        key=lambda i: (
            by_directory[i["directory_id"]]["name"],
            i["source_relative_path"],
            i["image_id"],
        )
    )
    names = export_names(samples, by_directory)
    for sample in samples:
        sample["output_name"] = names[sample["image_id"]]
    for d, stat in stats.items():
        for kind in ("positive", "negative"):
            total = stat[kind + "_images"]
            target = targets.get((d, kind), total if by_rule[d]["mode"] == "train" else 0)
            stat["target_train_" + kind + "_images"] = target
            stat["target_val_" + kind + "_images"] = total - target
            stat[kind + "_deviation"] = stat["train_" + kind + "_images"] - target
            ratio = by_rule[d].get("train_ratio")
            ratio = train_ratio if ratio is None else ratio
            stat[kind + "_deviation_reason"] = (
                "insufficient_samples"
                if by_rule[d]["mode"] == "ratio" and 0 < ratio < 1 and total == 1
                else "fixed_roles"
                if stat[kind + "_deviation"]
                and any(g["pin"] and (d, kind) in g["counts"] for g in candidates)
                else "exact_content_groups"
                if stat[kind + "_deviation"]
                or (0 < target < total and stat["train_" + kind + "_images"] in {0, total})
                else None
            )
        stat["target_train_images"] = sum(
            stat["target_train_" + k + "_images"] for k in ("positive", "negative")
        )
        stat["deviation"] = stat["train_images"] - stat["target_train_images"]
        stat["deviation_reason"] = (
            "exact_content_groups"
            if any(stat[k + "_deviation"] for k in ("positive", "negative"))
            else None
        )
    label_versions = [
        [label.id, label.version]
        for label in db.scalars(
            select(ProjectLabel)
            .where(ProjectLabel.project_id == project_id)
            .order_by(ProjectLabel.id)
        )
    ]
    source = {
        "project_type": "image",
        "split_seed": seed,
        "directory_rules": rules,
        "directories": list(by_directory.values()),
        "directory_stats": list(stats.values()),
        "samples": samples,
        "excluded": dict(excluded),
        "filtered_annotations": filtered,
        "stratification_warnings": [
            {"directory_id": d, "kind": kind, "reason": stat[kind + "_deviation_reason"]}
            for d, stat in stats.items()
            for kind in ("positive", "negative")
            if stat[kind + "_deviation_reason"]
        ],
    }
    for kind in ("positive", "negative"):
        source[kind + "_samples"] = {
            side: sum(s[side + "_" + kind + "_images"] for s in stats.values())
            for side in ("train", "val")
        }
        source["target_" + kind + "_samples"] = {
            side: sum(s["target_" + side + "_" + kind + "_images"] for s in stats.values())
            for side in ("train", "val")
        }
        source[kind + "_deviation"] = sum(s[kind + "_deviation"] for s in stats.values())
    source["fingerprint"] = fingerprint([source, revisions, labels, label_versions, train_ratio])
    assert len(samples) == sum(s["effective_images"] for s in stats.values())
    assert not (
        {s["content_sha256"] for s in samples if s["split"] == "train"}
        & {s["content_sha256"] for s in samples if s["split"] == "val"}
    )
    return source


def preview_response(source):
    samples = source["samples"]
    train = sum(s["split"] == "train" for s in samples)
    return {
        k: source[k]
        for k in (
            "fingerprint",
            "directory_stats",
            "excluded",
            "filtered_annotations",
            "positive_samples",
            "negative_samples",
            "target_positive_samples",
            "target_negative_samples",
            "positive_deviation",
            "negative_deviation",
            "stratification_warnings",
        )
    } | {
        "total_samples": len(samples),
        "train_samples": train,
        "val_samples": len(samples) - train,
        "actual_train_ratio": train / len(samples) if samples else 0,
        "single_training_hint": "单独训练还需训练集、验证集均非空，且训练集包含所选目标",
    }

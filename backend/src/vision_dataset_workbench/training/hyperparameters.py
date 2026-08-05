from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Literal

import yaml
from yaml.events import AliasEvent, DocumentStartEvent
from yaml.nodes import MappingNode

CATALOG_VERSION = "detect-v1"
SYSTEM_KEYS = {
    "task",
    "mode",
    "model",
    "data",
    "device",
    "project",
    "name",
    "exist_ok",
    "save_dir",
    "resume",
    "pretrained",
    "save",
    "save_period",
    "val",
    "plots",
    "profile",
    "time",
}


@dataclass(frozen=True)
class ParameterDefinition:
    key: str
    label: str
    group: str
    value_type: Literal[
        "integer", "number", "boolean", "string", "integer_or_null", "boolean_or_string"
    ]
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


def _number(
    key: str, label: str, group: str, default: float, minimum: float, maximum: float
) -> ParameterDefinition:
    return ParameterDefinition(key, label, group, "number", default, minimum, maximum)


CATALOG = (
    ParameterDefinition(
        "optimizer",
        "优化器",
        "优化",
        "string",
        "auto",
        choices=("auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp"),
    ),
    _number("lr0", "初始学习率", "优化", 0.01, 0, 1),
    _number("lrf", "最终学习率系数", "优化", 0.01, 0, 1),
    _number("momentum", "动量", "优化", 0.937, 0, 1),
    _number("weight_decay", "权重衰减", "优化", 0.0005, 0, 1),
    _number("warmup_epochs", "预热轮数", "优化", 3, 0, 10000),
    _number("warmup_momentum", "预热动量", "优化", 0.8, 0, 1),
    _number("warmup_bias_lr", "预热偏置学习率", "优化", 0.1, 0, 1),
    ParameterDefinition("nbs", "标称批量", "损失", "integer", 64, 1, 4096),
    _number("box", "框损失权重", "损失", 7.5, 0, 1000),
    _number("cls", "分类损失权重", "损失", 0.5, 0, 1000),
    _number("dfl", "DFL 损失权重", "损失", 1.5, 0, 1000),
    ParameterDefinition("workers", "数据线程", "数据加载", "integer", 8, 0, 256),
    ParameterDefinition(
        "cache", "缓存", "数据加载", "boolean_or_string", False, choices=("ram", "disk")
    ),
    ParameterDefinition("rect", "矩形训练", "数据加载", "boolean", False),
    _number("multi_scale", "多尺度幅度", "数据加载", 0, 0, 1),
    ParameterDefinition("close_mosaic", "关闭 Mosaic 轮数", "数据加载", "integer", 10, 0, 100000),
    _number("fraction", "数据使用比例", "数据加载", 1, 0.000001, 1),
    ParameterDefinition("seed", "随机种子", "数据加载", "integer", 0, 0, 2147483647),
    ParameterDefinition("deterministic", "确定性训练", "数据加载", "boolean", True),
    ParameterDefinition("single_cls", "单类别训练", "数据加载", "boolean", False),
    ParameterDefinition("freeze", "冻结层数", "数据加载", "integer_or_null", None, 0, 100000),
    _number("hsv_h", "色相增强", "图像增强", 0.015, 0, 1),
    _number("hsv_s", "饱和度增强", "图像增强", 0.7, 0, 1),
    _number("hsv_v", "亮度增强", "图像增强", 0.4, 0, 1),
    _number("degrees", "旋转角度", "图像增强", 0, 0, 180),
    _number("translate", "平移比例", "图像增强", 0.1, 0, 1),
    _number("scale", "缩放比例", "图像增强", 0.5, 0, 1),
    _number("shear", "剪切角度", "图像增强", 0, -180, 180),
    _number("perspective", "透视比例", "图像增强", 0, 0, 0.001),
    _number("flipud", "上下翻转概率", "图像增强", 0, 0, 1),
    _number("fliplr", "左右翻转概率", "图像增强", 0.5, 0, 1),
    _number("mosaic", "Mosaic 概率", "图像增强", 1, 0, 1),
    _number("mixup", "MixUp 概率", "图像增强", 0, 0, 1),
    ParameterDefinition("patience", "早停耐心值", "验证", "integer", 100, 0, 100000),
    ParameterDefinition("cos_lr", "余弦学习率", "验证", "boolean", False),
    ParameterDefinition("amp", "混合精度", "验证", "boolean", True),
)
DEFINITIONS = {item.key: item for item in CATALOG}
CORE_KEYS = {"epochs", "batch", "imgsz"}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    key: str | None = None
    line: int | None = None
    column: int | None = None


class HyperparameterValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        super().__init__(issues[0].message if issues else "invalid hyperparameters")
        self.issues = issues


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _UniqueSafeLoader, node: MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise HyperparameterValidationError(
                [
                    ValidationIssue(
                        "duplicate_key",
                        f"参数 {key} 重复",
                        str(key),
                        key_node.start_mark.line + 1,
                        key_node.start_mark.column + 1,
                    )
                ]
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def catalog_payload() -> dict[str, Any]:
    return {
        "version": CATALOG_VERSION,
        "items": [{**asdict(item), "choices": list(item.choices)} for item in CATALOG],
    }


def _issue(
    code: str, message: str, key: str | None = None, marks: dict[str, tuple[int, int]] | None = None
) -> ValidationIssue:
    mark = marks.get(key) if key and marks else None
    return ValidationIssue(code, message, key, mark[0] if mark else None, mark[1] if mark else None)


def _validate_definition(
    key: str, value: Any, definition: ParameterDefinition, marks: dict[str, tuple[int, int]]
) -> ValidationIssue | None:
    kind = definition.value_type
    valid = (
        (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
        or (kind == "boolean" and isinstance(value, bool))
        or (kind == "string" and isinstance(value, str))
        or (
            kind == "integer_or_null"
            and (value is None or (isinstance(value, int) and not isinstance(value, bool)))
        )
        or (kind == "boolean_or_string" and (isinstance(value, bool) or isinstance(value, str)))
    )
    if not valid:
        return _issue("invalid_type", f"参数 {key} 类型不正确", key, marks)
    if isinstance(value, float) and not isfinite(value):
        return _issue("invalid_number", f"参数 {key} 必须是有限数值", key, marks)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if definition.minimum is not None and value < definition.minimum:
            return _issue("out_of_range", f"参数 {key} 不能小于 {definition.minimum:g}", key, marks)
        if definition.maximum is not None and value > definition.maximum:
            return _issue("out_of_range", f"参数 {key} 不能大于 {definition.maximum:g}", key, marks)
    if isinstance(value, str) and definition.choices and value not in definition.choices:
        return _issue("invalid_choice", f"参数 {key} 不在允许选项中", key, marks)
    return None


def validate_values(
    values: dict[str, Any], marks: dict[str, tuple[int, int]] | None = None
) -> dict[str, Any]:
    marks = marks or {}
    issues: list[ValidationIssue] = []
    for key in CORE_KEYS:
        if key not in values:
            issues.append(_issue("missing_key", f"缺少核心参数 {key}", key, marks))
    epochs = values.get("epochs")
    imgsz = values.get("imgsz")
    batch = values.get("batch")
    if "epochs" in values and (
        not isinstance(epochs, int) or isinstance(epochs, bool) or not 1 <= epochs <= 100000
    ):
        issues.append(_issue("invalid_value", "epochs 必须是 1–100000 的整数", "epochs", marks))
    if "imgsz" in values and (
        not isinstance(imgsz, int)
        or isinstance(imgsz, bool)
        or not 32 <= imgsz <= 8192
        or imgsz % 32
    ):
        issues.append(
            _issue("invalid_value", "imgsz 必须是 32–8192 且为 32 的倍数", "imgsz", marks)
        )
    batch_valid = (
        isinstance(batch, int)
        and not isinstance(batch, bool)
        and (batch == -1 or 1 <= batch <= 4096)
    ) or (isinstance(batch, float) and isfinite(batch) and 0 < batch <= 1)
    if "batch" in values and not batch_valid:
        issues.append(
            _issue("invalid_value", "batch 必须为 -1、1–4096 整数或 (0,1] 小数", "batch", marks)
        )
    extra: dict[str, Any] = {}
    for key, value in values.items():
        if key in CORE_KEYS:
            continue
        if key in SYSTEM_KEYS:
            issues.append(_issue("system_key", f"参数 {key} 由系统控制", key, marks))
            continue
        definition = DEFINITIONS.get(key)
        if definition is None:
            issues.append(_issue("unknown_key", f"未知参数 {key}", key, marks))
            continue
        problem = _validate_definition(key, value, definition, marks)
        if problem:
            issues.append(problem)
        else:
            extra[key] = value
    if issues:
        raise HyperparameterValidationError(issues)
    assert isinstance(epochs, int) and isinstance(imgsz, int)
    if batch == -1:
        batch_mode, batch_value = "auto", None
    elif isinstance(batch, int):
        batch_mode, batch_value = "fixed", float(batch)
    else:
        batch_mode, batch_value = "fraction", float(batch)
    return {
        "epochs": epochs,
        "batch_mode": batch_mode,
        "batch_value": batch_value,
        "image_size": imgsz,
        "extra_parameters": extra,
    }


def parse_raw(raw: str) -> dict[str, Any]:
    try:
        document_count = 0
        for event in yaml.parse(raw):
            if isinstance(event, DocumentStartEvent):
                document_count += 1
            if isinstance(event, AliasEvent) or getattr(event, "anchor", None):
                raise HyperparameterValidationError(
                    [ValidationIssue("yaml_feature", "不允许 YAML 锚点或别名")]
                )
        if document_count > 1:
            raise HyperparameterValidationError(
                [ValidationIssue("multiple_documents", "只允许一个 YAML 文档")]
            )
        node = yaml.compose(raw, Loader=yaml.SafeLoader)
        if not isinstance(node, MappingNode):
            raise HyperparameterValidationError(
                [ValidationIssue("invalid_shape", "RAW 必须是单层 YAML 映射")]
            )
        marks: dict[str, tuple[int, int]] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node.value, str):
                raise HyperparameterValidationError(
                    [ValidationIssue("invalid_key", "参数 key 必须是字符串")]
                )
            marks[key_node.value] = (key_node.start_mark.line + 1, key_node.start_mark.column + 1)
            if isinstance(value_node, MappingNode) or value_node.id == "sequence":
                raise HyperparameterValidationError(
                    [
                        _issue(
                            "nested_value",
                            f"参数 {key_node.value} 不能使用嵌套值",
                            key_node.value,
                            marks,
                        )
                    ]
                )
        values = yaml.load(raw, Loader=_UniqueSafeLoader)
    except HyperparameterValidationError:
        raise
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise HyperparameterValidationError(
            [
                ValidationIssue(
                    "yaml_syntax",
                    "YAML 语法不合法",
                    line=mark.line + 1 if mark else None,
                    column=mark.column + 1 if mark else None,
                )
            ]
        ) from exc
    return validate_values(values)


def effective_parameters(
    epochs: int,
    batch_mode: str,
    batch_value: float | None,
    image_size: int,
    extra_parameters: dict[str, Any],
) -> dict[str, Any]:
    batch: int | float = (
        -1
        if batch_mode == "auto"
        else int(batch_value or 0)
        if batch_mode == "fixed"
        else float(batch_value or 0)
    )
    return {"epochs": epochs, "batch": batch, "imgsz": image_size, **extra_parameters}

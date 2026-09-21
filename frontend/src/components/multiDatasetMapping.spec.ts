import { describe, expect, it } from "vitest";
import type { TrainingResources } from "../api/training";
import {
  canonicalMapping,
  deleteTarget,
  mappingDraft,
  moveTarget,
  restoreTargets,
  syncMapping,
  targetSources,
} from "./multiDatasetMapping";

const datasets: TrainingResources["datasets"] = [
  {
    id: "a", name: "A", project_id: "p", project_name: "P", total_frames: 2,
    train_frames: 1, val_frames: 1,
    labels: [{ index: 0, name: " car " }, { index: 1, name: "Person" }],
  },
  {
    id: "b", name: "B", project_id: "p", project_name: "P", total_frames: 3,
    train_frames: 2, val_frames: 1,
    labels: [{ index: 2, name: "car" }, { index: 4, name: "plane" }],
  },
];

describe("multi dataset mapping", () => {
  it("groups trimmed exact names while keeping case significant", () => {
    const draft = mappingDraft(
      { version: 1, dataset_export_ids: ["a", "b"], target_classes: ["plane", "car"] },
      datasets,
    );
    expect(draft.order).toEqual(["plane", "car", "Person"]);
    expect(targetSources("car", draft.selected, datasets)).toHaveLength(2);
  });

  it("keeps selection order, removes unavailable rows and restores deleted rows", () => {
    const draft = mappingDraft(null, datasets);
    draft.selected.push("b", "a");
    syncMapping(draft, datasets);
    expect(draft.order).toEqual(["car", "plane", "Person"]);
    moveTarget(draft, 2, -1);
    deleteTarget(draft, "car");
    expect(draft.order).toEqual(["Person", "plane"]);
    restoreTargets(draft, datasets);
    expect(canonicalMapping(draft)).toEqual({
      version: 1,
      dataset_export_ids: ["b", "a"],
      target_classes: ["Person", "plane", "car"],
    });
    draft.selected = ["b"];
    syncMapping(draft, datasets);
    expect(draft.order).toEqual(["plane", "car"]);
  });
});

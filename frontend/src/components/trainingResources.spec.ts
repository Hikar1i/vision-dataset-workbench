import { describe, expect, it } from "vitest";
import {
  applyHyperparameterOverrides,
  artifactPreview,
  diffHyperparameterConfig,
  effectiveResourceIds,
  groupedOptions,
  hasEffectiveResources,
  hyperparameterOverrideCount,
  missingEffectiveResources,
} from "./trainingResources";

const row = {
  name: "model", description: "", dataset_export_id: null, template_id: null,
  dataset_mode: "inherit", multi_dataset_config: null,
  base_model_id: "base-row", epochs_override: null, batch_mode_override: null,
  batch_value_override: null, image_size_override: null, gpu_index: 0, queue_order: 1,
  extra_parameters_override: null,
} as const;
const defaults = {
  default_dataset_export_id: "dataset-default",
  default_dataset_mode: "single" as const,
  default_multi_dataset_config: null,
  default_template_id: "template-default",
  default_epochs_override: null,
  default_batch_mode_override: null,
  default_batch_value_override: null,
  default_image_size_override: null,
  default_extra_parameters_override: null,
  default_base_model_id: "base-default",
};
const readinessResources = {
  datasets: [
    { id: "dataset-default", name: "D", project_id: "p", project_name: "P", total_frames: 1, train_frames: 1, val_frames: 0, labels: [] },
  ],
  templates: [
    { id: "template-default", name: "T", description: "", epochs: 100, batch_mode: "auto" as const, batch_value: null, image_size: 640, extra_parameters: {}, effective_parameters: {}, version: 1, updated_at: "2026-08-20T00:00:00Z", can_edit: false },
  ],
  base_models: [
    { id: "base-row", name: "B", model_code: "b.pt", project_id: "p", project_name: "P" },
  ],
};

describe("training resources", () => {
  it("reports effective resource gaps across inherited and mixed sources", () => {
    expect(missingEffectiveResources(row, defaults, readinessResources)).toEqual([]);
    expect(missingEffectiveResources(
      { ...row, base_model_id: null },
      { ...defaults, default_base_model_id: null },
      readinessResources,
    )).toEqual(["baseModel"]);
    expect(missingEffectiveResources(
      {
        ...row,
        dataset_mode: "multi",
        multi_dataset_config: { version: 1, dataset_export_ids: ["dataset-default"], target_classes: [] },
      },
      defaults,
      readinessResources,
    )).toEqual(["dataset"]);
  });

  it("uses model resources before task defaults", () => {
    expect(effectiveResourceIds(row, defaults)).toEqual({
      datasetMode: "single", datasetId: "dataset-default", multiDatasetConfig: null,
      templateId: "template-default", baseModelId: "base-row",
    });
    expect(hasEffectiveResources(row, defaults, readinessResources)).toBe(true);
    expect(hasEffectiveResources(
      { ...row, dataset_mode: "multi", dataset_export_id: null, multi_dataset_config: { version: 1, dataset_export_ids: ["dataset-default"], target_classes: ["car"] } },
      defaults,
      readinessResources,
    )).toBe(true);
    expect(hasEffectiveResources(
      { ...row, dataset_mode: "multi", dataset_export_id: null, multi_dataset_config: null },
      defaults,
      readinessResources,
    )).toBe(false);
  });

  it("groups resources and previews effective artifact parameters", () => {
    expect(groupedOptions([{ id: "d", name: "Export", project_id: "p", project_name: "Project" }]))
      .toEqual([{ value: "p", label: "Project", children: [{ value: "d", label: "Export" }] }]);
    const preview = artifactPreview(row, defaults, {
      datasets: [],
      templates: [{ id: "template-default", name: "T", description: "", epochs: 100, batch_mode: "fraction", batch_value: .8, image_size: 640, extra_parameters: {}, effective_parameters: {}, version: 1, updated_at: "2026-01-01T00:00:00Z", can_edit: false }],
      base_models: [{ id: "base-row", name: "YOLO", model_code: "YOLO11n.pt", project_id: "p", project_name: "P" }],
    }, "firedet");
    expect(preview).toMatch(/-yolo11n-pt-s640-b80pct-e100$/);
  });

  it("creates sparse extra-parameter diffs and reapplies them", () => {
    const base = {
      epochs: 100,
      batch_mode: "auto" as const,
      batch_value: null,
      image_size: 640,
      extra_parameters: { lr0: 0.01, patience: 50 },
    };
    const edited = {
      epochs: 200,
      batch_mode: "fixed" as const,
      batch_value: 16,
      image_size: 640,
      extra_parameters: { lr0: 0.005, mosaic: 0.8 },
    };
    const diff = diffHyperparameterConfig(base, edited);

    expect(diff.extra).toEqual({
      version: 1,
      set: { lr0: 0.005, mosaic: 0.8 },
      remove: ["patience"],
    });
    expect(hyperparameterOverrideCount(diff)).toBe(5);
    expect(applyHyperparameterOverrides(base, diff)).toEqual(edited);
  });
});

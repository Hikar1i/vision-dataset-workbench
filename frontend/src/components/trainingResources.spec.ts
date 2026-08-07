import { describe, expect, it } from "vitest";
import { artifactPreview, effectiveResourceIds, groupedOptions, hasEffectiveResources } from "./trainingResources";

const row = {
  name: "model", description: "", dataset_export_id: null, template_id: null,
  base_model_id: "base-row", epochs_override: null, batch_mode_override: null,
  batch_value_override: null, image_size_override: null, gpu_index: 0, queue_order: 1,
} as const;
const defaults = {
  default_dataset_export_id: "dataset-default",
  default_template_id: "template-default",
  default_base_model_id: "base-default",
};

describe("training resources", () => {
  it("uses model resources before task defaults", () => {
    expect(effectiveResourceIds(row, defaults)).toEqual({
      datasetId: "dataset-default", templateId: "template-default", baseModelId: "base-row",
    });
    expect(hasEffectiveResources(row, defaults)).toBe(true);
  });

  it("groups resources and previews effective artifact parameters", () => {
    expect(groupedOptions([{ id: "d", name: "Export", project_id: "p", project_name: "Project" }]))
      .toEqual([{ value: "p", label: "Project", children: [{ value: "d", label: "Export" }] }]);
    const preview = artifactPreview(row, defaults, {
      datasets: [],
      templates: [{ id: "template-default", name: "T", epochs: 100, batch_mode: "fraction", batch_value: .8, image_size: 640 }],
      base_models: [{ id: "base-row", name: "YOLO", model_code: "YOLO11n.pt", project_id: "p", project_name: "P" }],
    }, "firedet");
    expect(preview).toMatch(/-yolo11n-pt-s640-b80pct-e100$/);
  });
});

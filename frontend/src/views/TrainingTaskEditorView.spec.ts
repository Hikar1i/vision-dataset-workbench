import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve("src/views/TrainingTaskEditorView.vue"), "utf8");

describe("TrainingTaskEditorView layout", () => {
  it("places the training-mode selector at the top of the model execution section", () => {
    const section = source.indexOf("训练模型与执行顺序");
    const selector = source.indexOf('class="training-mode-field"');
    const editor = source.indexOf("<TrainingModelEditor");

    expect(section).toBeGreaterThan(-1);
    expect(selector).toBeGreaterThan(section);
    expect(selector).toBeLessThan(editor);
  });

  it("keeps task and model multi-dataset mappings as explicit saved configuration", () => {
    expect(source).toContain("form.default_multi_dataset_config = config");
    expect(source).toContain("mappingModel.value.multi_dataset_config = config");
    expect(source).toContain("initialMapping(form.default_dataset_export_id)");
    expect(source).toContain('form.default_dataset_mode === "multi" && !form.default_multi_dataset_config');
  });
});

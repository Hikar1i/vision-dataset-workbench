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

  it("uses the shared dataset summary and an explicit empty single-dataset placeholder", () => {
    expect(source).toContain('placeholder="未选择任何数据集"');
    expect(source).toContain("<DatasetSelectionSummary");
    expect(source).toContain(':dataset-id="form.default_dataset_export_id"');
    expect(source).toContain(':config="form.default_multi_dataset_config"');
    expect(source).toContain('@configure-mapping="openTaskMapping"');
    expect(source).not.toContain('class="multi-summary"');
  });

  it("integrates task and explicit-model hyperparameter editing with persistent feedback", () => {
    expect(source).toContain('<CoreHyperparameterFields')
    expect(source).toContain('<TrainingHyperparameterDialog')
    expect(source).toContain('编辑完整超参数')
    expect(source).toContain('已应用修改：${count} 项覆盖将在保存草稿时生效。')
    expect(source).toContain('模板已更新至 v${taskNext.version}')
    expect(source).toContain('window.addEventListener("focus", refreshResources)')
    expect(source).toContain('保留覆盖并应用到新模板')
    expect(source).toContain('清空覆盖并使用新模板')
    expect(source).toContain("finishTemplateSwitch('cancel')")
  });
});

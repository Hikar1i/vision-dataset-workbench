import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TrainingModelDraft, TrainingResources } from "../api/training";
import TrainingModelEditor from "./TrainingModelEditor.vue";

const model = (): TrainingModelDraft => ({
  name: "检测模型",
  description: "",
  dataset_export_id: null,
  dataset_mode: "inherit",
  multi_dataset_config: null,
  template_id: null,
  base_model_id: null,
  epochs_override: null,
  batch_mode_override: null,
  batch_value_override: null,
  image_size_override: null,
  gpu_index: 0,
  queue_order: 1,
});

const resources: TrainingResources = {
  datasets: [
    { id: "d1", name: "车辆集", project_id: "p", project_name: "项目", total_frames: 120, train_frames: 100, val_frames: 20, labels: [{ index: 0, name: "car" }] },
  ],
  templates: [],
  base_models: [],
};

describe("TrainingModelEditor", () => {
  it("opens mapping when a model first switches to multi-dataset mode", async () => {
    const row = model();
    const wrapper = mount(TrainingModelEditor, {
      props: {
        models: [row], resources, devices: [], mode: "single_model", taskCode: "demo",
        defaults: { default_dataset_export_id: null, default_dataset_mode: "single", default_multi_dataset_config: null, default_template_id: null, default_base_model_id: null },
      },
      global: {
        stubs: {
          ElSegmented: {
            props: ["modelValue", "options"],
            emits: ["change"],
            template: '<button data-test="multi" @click="$emit(\'change\', \'multi\')">自定义多数据集</button>',
          },
          ElForm: { template: "<form><slot /></form>" },
          ElFormItem: { template: "<label><slot /></label>" },
          ElInput: true, ElSelect: true, ElOption: true, ElInputNumber: true,
          ElCascader: true, ElSwitch: true, ElSlider: true, ElIcon: true,
        },
      },
    });

    await wrapper.get('[data-test="multi"]').trigger("click");

    expect(row.dataset_mode).toBe("multi");
    expect(wrapper.emitted("configureMapping")?.[0]).toEqual([row]);
  });

  it("summarizes inherited multi-dataset configuration in a collapsed card", () => {
    const row = model();
    const wrapper = mount(TrainingModelEditor, {
      props: {
        models: [row], resources, devices: [], mode: "single_model", taskCode: "demo",
        defaults: { default_dataset_export_id: null, default_dataset_mode: "multi", default_multi_dataset_config: { version: 1, dataset_export_ids: ["d1"], target_classes: ["car"] }, default_template_id: null, default_base_model_id: null },
      },
      global: { stubs: { ElForm: { template: "<form><slot /></form>" }, ElFormItem: { template: "<label><slot /></label>" }, ElSegmented: true, ElInput: true, ElSelect: true, ElOption: true, ElInputNumber: true, ElCascader: true, ElSwitch: true, ElSlider: true, ElIcon: true } },
    });

    expect(wrapper.text()).toContain("1 个数据集 · 1 个目标类别 · 120 张图像");
  });
});

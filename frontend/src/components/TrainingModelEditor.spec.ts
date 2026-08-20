import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TrainingModelDraft, TrainingResources } from "../api/training";
import type { TrainingDefaults } from "./trainingResources";
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
  extra_parameters_override: null,
  gpu_index: 0,
  queue_order: 1,
});

const resources: TrainingResources = {
  datasets: [
    { id: "d1", name: "车辆集", project_id: "p", project_name: "项目", total_frames: 120, train_frames: 100, val_frames: 20, labels: [{ index: 0, name: "car" }] },
  ],
  templates: [
    {
      id: "t1", name: "基础模板", description: "", epochs: 100, batch_mode: "auto",
      batch_value: null, image_size: 640, extra_parameters: {}, effective_parameters: {},
      version: 2, updated_at: "2026-08-18T00:00:00Z", can_edit: true,
    },
  ],
  base_models: [],
};

const defaults: TrainingDefaults = {
  default_dataset_export_id: null,
  default_dataset_mode: "single" as const,
  default_multi_dataset_config: null,
  default_template_id: null,
  default_epochs_override: null,
  default_batch_mode_override: null,
  default_batch_value_override: null,
  default_image_size_override: null,
  default_extra_parameters_override: null,
  default_base_model_id: null,
};

const stubs = {
  ElSegmented: {
    props: ["modelValue", "options"],
    emits: ["change"],
    template: `<div>
      <button v-for="option in options" :key="option.value" :data-test="option.value" @click="$emit('change', option.value)">{{ option.label }}</button>
    </div>`,
  },
  ElForm: { template: "<form><slot /></form>" },
  ElFormItem: {
    props: ["error"],
    template: "<label><slot name='label' /><slot />{{ error }}</label>",
  },
  ElCascader: {
    props: ["placeholder"],
    template: '<div data-test="dataset-cascader">{{ placeholder }}</div>',
  },
  ElInput: true,
  ElSelect: true,
  ElOption: true,
  ElInputNumber: true,
  ElSwitch: true,
  ElSlider: true,
  ElIcon: true,
};

function mountEditor(row: TrainingModelDraft, taskDefaults: TrainingDefaults = defaults) {
  return mount(TrainingModelEditor, {
    props: {
      models: [row],
      resources,
      devices: [],
      mode: "single_model",
      taskCode: "demo",
      defaults: taskDefaults,
    },
    global: { stubs },
  });
}

describe("TrainingModelEditor", () => {
  it("opens mapping when a model first switches to multi-dataset mode", async () => {
    const row = model();
    const wrapper = mountEditor(row);

    await wrapper.get('[data-test="multi"]').trigger("click");

    expect(row.dataset_mode).toBe("multi");
    expect(wrapper.emitted("configureMapping")?.[0]).toEqual([row]);
  });

  it("summarizes inherited multi-dataset configuration in a collapsed card", () => {
    const row = model();
    const wrapper = mountEditor(row, {
      ...defaults,
      default_dataset_mode: "multi",
      default_multi_dataset_config: { version: 1, dataset_export_ids: ["d1"], target_classes: ["car"] },
    });

    expect(wrapper.text()).toContain("1 个数据集 · 1 个目标类别 · 120 张图像");
    expect(wrapper.find('[data-test="configure-mapping"]').exists()).toBe(false);
  });

  it("uses concise mode labels and retains dormant settings when inheriting", async () => {
    const savedConfig = { version: 1 as const, dataset_export_ids: ["d1"], target_classes: ["car"] };
    const row = { ...model(), dataset_mode: "multi" as const, dataset_export_id: "d1", multi_dataset_config: savedConfig };
    const wrapper = mountEditor(row);

    expect(wrapper.text()).toContain("继承任务默认");
    expect(wrapper.text()).toContain("单数据集");
    expect(wrapper.text()).toContain("多数据集");
    expect(wrapper.text()).not.toContain("自定义单数据集");
    expect(wrapper.text()).not.toContain("自定义多数据集");
    expect(wrapper.text()).not.toContain("恢复任务默认");
    expect(wrapper.find('[data-test="configure-mapping"]').exists()).toBe(true);

    await wrapper.get('[data-test="inherit"]').trigger("click");
    expect(row.dataset_mode).toBe("inherit");
    expect(row.dataset_export_id).toBe("d1");
    expect(row.multi_dataset_config).toEqual(savedConfig);
    expect(wrapper.find('[data-test="configure-mapping"]').exists()).toBe(false);
  });

  it("shows single-dataset details with the explicit empty placeholder", () => {
    const row = { ...model(), dataset_mode: "single" as const, dataset_export_id: "d1" };
    const wrapper = mountEditor(row);

    expect(wrapper.get('[data-test="dataset-cascader"]').text()).toBe("未选择任何数据集");
    expect(wrapper.text()).toContain("120 张图像 · 1 个类别");
    expect(wrapper.text()).toContain("0 : car");
    expect(wrapper.find('[data-test="configure-mapping"]').exists()).toBe(false);
  });

  it("hides model hyperparameter editing while inheriting and shows it for an explicit template", async () => {
    const inherited = model();
    const inheritedWrapper = mountEditor(inherited, {
      ...defaults,
      default_template_id: "t1",
      default_epochs_override: 120,
    });
    expect(inheritedWrapper.text()).toContain("基础模板 · v2 · 1 项覆盖");
    expect(inheritedWrapper.text()).not.toContain("编辑完整超参数");

    const explicit = { ...model(), template_id: "t1" };
    const explicitWrapper = mountEditor(explicit);
    expect(explicitWrapper.text()).toContain("基础模板 · v2");
    expect(explicitWrapper.text()).toContain("编辑完整超参数");
    expect(explicitWrapper.findComponent({ name: "ElSwitch" }).attributes("aria-label")).toBe("核心参数覆盖");

    const select = explicitWrapper.findComponent({ name: "ElSelect" });
    expect(select.exists()).toBe(true);
  });

  it("shows inherited resource names and inline launch gaps", () => {
    const wrapper = mountEditor(model(), { ...defaults, default_template_id: "t1" });

    expect(wrapper.text()).toContain("已继承：基础模板");
    expect(wrapper.text()).toContain("未配置：请在任务总体设置中提供默认值，或在当前模型中选择。");
    expect(wrapper.text()).toContain("启动必填");
  });
});

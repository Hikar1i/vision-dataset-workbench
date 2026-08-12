import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import GpuSequenceEditor from "./GpuSequenceEditor.vue";
import type { GpuDevice, TrainingModelDraft } from "../api/training";

const row = (name: string, gpu: number, order: number): TrainingModelDraft => ({
  name,
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
  gpu_index: gpu,
  queue_order: order,
});

describe("GpuSequenceEditor", () => {
  it("renders GPU lanes and changes the strict serial order with accessible buttons", async () => {
    const models = [
      row("first", 0, 1),
      row("second", 0, 2),
      row("other gpu", 1, 1),
    ];
    const devices: GpuDevice[] = [
      {
        index: 0,
        name: "A4000",
        memory_total_mb: 16000,
        memory_used_mb: 4000,
        memory_percent: 25,
        utilization_percent: 2,
        level: "green",
      },
      {
        index: 1,
        name: "RTX 4000",
        memory_total_mb: 8000,
        memory_used_mb: 7000,
        memory_percent: 87.5,
        utilization_percent: 80,
        level: "red",
      },
    ];
    const wrapper = mount(GpuSequenceEditor, {
      props: { models, devices },
      global: {
        stubs: {
          ElTag: { template: "<span><slot /></span>" },
          ElEmpty: { template: "<div />" },
          ElSelect: { template: "<select />" },
          ElOption: { template: "<option />" },
          ElButton: {
            props: ["title", "ariaLabel"],
            emits: ["click"],
            template:
              '<button :title="title" :aria-label="ariaLabel" @click="$emit(\'click\')"><slot /></button>',
          },
        },
      },
    });
    expect(wrapper.text()).toContain("GPU 0");
    expect(wrapper.text()).toContain("显存 87.5%");
    const upButtons = wrapper.findAll('button[title="上移"]');
    await upButtons[1].trigger("click");
    expect(models.map((item) => item.queue_order)).toEqual([2, 1, 1]);
    expect(wrapper.emitted("change")).toHaveLength(1);
  });
});

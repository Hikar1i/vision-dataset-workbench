import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import type { MultiDatasetConfig, TrainingResources } from "../api/training";
import DatasetSelectionSummary from "./DatasetSelectionSummary.vue";

const datasets: TrainingResources["datasets"] = [
  {
    id: "dataset-a",
    name: "车辆与航空器数据集",
    project_id: "project-a",
    project_name: "综合目标项目",
    total_frames: 320,
    train_frames: 280,
    val_frames: 40,
    labels: [
      { index: 5, name: "smoke" },
      { index: 0, name: "car" },
      { index: 1, name: "plane" },
    ],
  },
  {
    id: "dataset-b",
    name: "消防数据集",
    project_id: "project-b",
    project_name: "火灾检测项目",
    total_frames: 200,
    train_frames: 160,
    val_frames: 40,
    labels: [{ index: 0, name: "fire" }],
  },
];

let resizeCallback: ResizeObserverCallback;

class ResizeObserverMock {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback;
  }

  observe() {}
  disconnect() {}
}

function mountSummary(overrides: {
  mode: "single" | "multi";
  datasetId?: string | null;
  config?: MultiDatasetConfig | null;
  allowConfigure?: boolean;
}) {
  return mount(DatasetSelectionSummary, {
    props: { datasets, ...overrides },
  });
}

describe("DatasetSelectionSummary", () => {
  beforeEach(() => vi.stubGlobal("ResizeObserver", ResizeObserverMock));
  afterEach(() => vi.unstubAllGlobals());

  it("renders nothing for an empty single-dataset selection", () => {
    expect(mountSummary({ mode: "single", datasetId: null }).text()).toBe("");
  });

  it("renders single-dataset totals and classes in source-index order", () => {
    const wrapper = mountSummary({ mode: "single", datasetId: "dataset-a" });

    expect(wrapper.text()).toContain("320 张图像 · 3 个类别");
    expect(wrapper.findAll(".class-chip").map((item) => item.text())).toEqual([
      "0 : car",
      "1 : plane",
      "5 : smoke",
    ]);
    expect(wrapper.find('[data-test="configure-mapping"]').exists()).toBe(false);
  });

  it("renders multi-dataset totals and separate expandable chip groups", async () => {
    const wrapper = mountSummary({
      mode: "multi",
      config: {
        version: 1,
        dataset_export_ids: ["dataset-a", "dataset-b"],
        target_classes: ["car", "plane", "smoke"],
      },
    });
    const datasetList = wrapper.get('[data-test="dataset-chip-list"]').element;
    const classList = wrapper.get('[data-test="class-chip-list"]').element;
    Object.defineProperties(datasetList, {
      clientHeight: { value: 60 },
      scrollHeight: { value: 120 },
    });
    Object.defineProperties(classList, {
      clientHeight: { value: 60 },
      scrollHeight: { value: 120 },
    });
    resizeCallback([], {} as ResizeObserver);
    await nextTick();

    expect(wrapper.text()).toContain("2 个数据集 · 520 张图像");
    expect(wrapper.text()).toContain("3 个目标类别");
    const datasetToggle = wrapper.get('[aria-label="展开全部数据集"]');
    const classToggle = wrapper.get('[aria-label="展开全部类别"]');
    expect(datasetToggle.attributes("aria-expanded")).toBe("false");
    expect(classToggle.attributes("aria-expanded")).toBe("false");

    await datasetToggle.trigger("click");
    expect(wrapper.get('[data-test="dataset-chip-list"]').classes()).toContain("expanded");
    expect(wrapper.get('[data-test="class-chip-list"]').classes()).not.toContain("expanded");
  });

  it("only exposes an enabled mapping action when allowed in multi mode", async () => {
    const multi = mountSummary({ mode: "multi", config: null });
    await multi.get('[data-test="configure-mapping"]').trigger("click");
    expect(multi.emitted("configureMapping")).toHaveLength(1);

    const inherited = mountSummary({ mode: "multi", config: null, allowConfigure: false });
    expect(inherited.find('[data-test="configure-mapping"]').exists()).toBe(false);
  });
});

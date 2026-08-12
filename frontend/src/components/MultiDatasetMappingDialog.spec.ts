import { DOMWrapper, flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { afterEach, expect, it } from "vitest";
import MultiDatasetMappingDialog from "./MultiDatasetMappingDialog.vue";

const datasets = [
  {
    id: "a", name: "道路集", project_id: "p", project_name: "道路项目",
    total_frames: 10, train_frames: 8, val_frames: 2,
    labels: [{ index: 0, name: "car" }, { index: 1, name: "plane" }],
  },
];

afterEach(() => { document.body.innerHTML = ""; });

it("uses a working copy and only emits canonical config on save", async () => {
  const wrapper = mount(MultiDatasetMappingDialog, {
    attachTo: document.body,
    props: {
      modelValue: true,
      config: { version: 1, dataset_export_ids: ["a"], target_classes: ["car", "plane"] },
      datasets,
    },
    global: { plugins: [ElementPlus] },
  });
  await flushPromises();
  const body = new DOMWrapper(document.body);
  expect(body.text()).toContain("目标类别映射");
  await body.findAll('button[aria-label="删除目标类别"]')[0]!.trigger("click");
  await body.get(".mapping-dialog .el-dialog__headerbtn").trigger("click");
  expect(wrapper.emitted("save")).toBeUndefined();

  await wrapper.setProps({ modelValue: false });
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  expect(new DOMWrapper(document.body).findAll(".mapping-row:not(.mapping-head)")).toHaveLength(2);
  await new DOMWrapper(document.body).get('[data-test="save-mapping"]').trigger("click");
  expect(wrapper.emitted("save")?.at(-1)).toEqual([
    { version: 1, dataset_export_ids: ["a"], target_classes: ["car", "plane"] },
  ]);
});

it("disables save when no dataset is selected and exposes project expansion state", async () => {
  mount(MultiDatasetMappingDialog, {
    attachTo: document.body,
    props: { modelValue: true, config: null, datasets },
    global: { plugins: [ElementPlus] },
  });
  await flushPromises();
  const body = new DOMWrapper(document.body);
  expect(body.get(".project-title").attributes("aria-expanded")).toBe("true");
  expect(body.get('[data-test="save-mapping"]').attributes("disabled")).toBeDefined();
  expect(body.text()).toContain("至少选择一个数据集");
});

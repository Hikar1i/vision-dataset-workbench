import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve("src/views/TrainingModelDetailView.vue"), "utf8");

describe("TrainingModelDetailView disclosure controls", () => {
  it.each([
    ["raw-parameters-panel", "完整超参数"],
    ["training-metrics-panel", "训练指标"],
    ["evaluation-curves-panel", "评估曲线"],
    ["training-log-panel", "训练日志"],
  ])("links the %s control to its labelled panel", (id, label) => {
    expect(source).toContain(`aria-controls="${id}"`);
    expect(source).toContain(`id="${id}"`);
    expect(source).toContain(`'收起${label}'`);
    expect(source).toContain(`'展开${label}'`);
  });
});

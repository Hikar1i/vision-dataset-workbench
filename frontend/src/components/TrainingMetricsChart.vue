<script setup lang="ts">
import { LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { TrainingMetric } from "../api/training";

const props = defineProps<{ metrics: TrainingMetric[] }>();
const root = ref<HTMLDivElement>();
use([
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
let chart: ECharts | undefined;
function render() {
  if (!chart) return;
  const epoch = props.metrics.map((item) => item.epoch);
  chart.setOption(
    {
      animationDuration: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 280,
      color: [
        "#16866f",
        "#d97706",
        "#2563eb",
        "#7c3aed",
        "#dc2626",
        "#0891b2",
        "#4d7c0f",
      ],
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      legend: { top: 4, type: "scroll" },
      grid: [
        { left: 54, right: 26, top: 42, height: "28%" },
        { left: 54, right: 26, top: "42%", height: "24%" },
        { left: 54, right: 26, top: "73%", bottom: 40 },
      ],
      xAxis: [0, 1, 2].map((gridIndex) => ({
        type: "category",
        gridIndex,
        data: epoch,
        axisPointer: { show: true },
        name: gridIndex === 2 ? "epoch" : "",
      })),
      yAxis: [
        { type: "value", gridIndex: 0, name: "loss" },
        { type: "value", gridIndex: 1, name: "lr" },
        { type: "value", gridIndex: 2, name: "score", min: 0, max: 1 },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1, 2] },
        { type: "slider", xAxisIndex: [0, 1, 2], bottom: 4, height: 18 },
      ],
      series: [
        ["box loss", "box_loss", 0, 0],
        ["cls loss", "cls_loss", 0, 0],
        ["learning rate", "learning_rate", 1, 1],
        ["precision", "precision", 2, 2],
        ["recall", "recall", 2, 2],
        ["mAP50", "map50", 2, 2],
        ["mAP50-95", "map50_95", 2, 2],
      ].map(([name, key, xAxisIndex, yAxisIndex]) => ({
        name,
        type: "line",
        xAxisIndex,
        yAxisIndex,
        showSymbol: false,
        connectNulls: true,
        data: props.metrics.map((item) => item[key as keyof TrainingMetric]),
      })),
    },
    true,
  );
}
function resize() {
  chart?.resize();
}
onMounted(() => {
  if (root.value) {
    chart = init(root.value);
    render();
    window.addEventListener("resize", resize);
  }
});
watch(() => props.metrics, render, { deep: true });
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>
<template>
  <div
    ref="root"
    class="metrics-chart"
    role="img"
    aria-label="训练损失、学习率与评估指标随 epoch 变化曲线"
  />
</template>
<style scoped>
.metrics-chart {
  width: 100%;
  height: 620px;
}
</style>

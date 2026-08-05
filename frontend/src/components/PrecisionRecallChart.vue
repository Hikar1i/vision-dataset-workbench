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
import type { PrCurve } from "../api/training";
use([
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
const props = defineProps<{ curve: PrCurve }>();
const root = ref<HTMLDivElement>();
let chart: ECharts | undefined;
function render() {
  if (!chart || props.curve.kind !== "interactive") return;
  chart.setOption(
    {
      animationDuration: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 280,
      tooltip: {
        trigger: "item",
        axisPointer: { type: "cross" },
        formatter: (item: any) =>
          `${item.seriesName}<br/>Recall ${Number(item.value[0]).toFixed(4)}<br/>Precision ${Number(item.value[1]).toFixed(4)}`,
      },
      legend: { type: "scroll", top: 0 },
      grid: { left: 58, right: 24, top: 42, bottom: 48 },
      xAxis: { type: "value", name: "Recall", min: 0, max: 1 },
      yAxis: { type: "value", name: "Precision", min: 0, max: 1 },
      dataZoom: [{ type: "inside" }, { type: "slider", bottom: 5, height: 18 }],
      series: props.curve.series.map((item) => ({
        name: item.name,
        type: "line",
        showSymbol: false,
        data: item.points,
        emphasis: { focus: "series" },
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
watch(() => props.curve, render, { deep: true });
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>
<template>
  <div
    v-if="curve.kind === 'interactive'"
    ref="root"
    class="pr-chart"
    role="img"
    aria-label="可交互 Precision Recall 曲线"
  />
  <img
    v-else-if="curve.kind === 'image'"
    :src="curve.url"
    alt="Precision Recall 曲线"
  /><el-empty v-else description="本次运行没有可用的 P-R 曲线" />
</template>
<style scoped>
.pr-chart {
  width: 100%;
  height: 420px;
}
img {
  display: block;
  max-width: 100%;
  margin: auto;
}
</style>

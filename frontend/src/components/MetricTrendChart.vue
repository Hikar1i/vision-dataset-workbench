<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { TrainingMetric } from "../api/training";

const props = defineProps<{
  metrics: TrainingMetric[];
  valueKey: keyof TrainingMetric;
  label: string;
  color?: string;
  score?: boolean;
}>();
const root = ref<HTMLDivElement>();
use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);
let chart: ECharts | undefined;
function render() {
  chart?.setOption({
    animationDuration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 220,
    color: [props.color || "#16866f"],
    tooltip: { trigger: "axis", axisPointer: { type: "cross" }, valueFormatter: (value: unknown) => Number(value).toPrecision(5) },
    grid: { left: 46, right: 16, top: 18, bottom: 35 },
    xAxis: { type: "category", name: "epoch", data: props.metrics.map(({ epoch }) => epoch), boundaryGap: false },
    yAxis: { type: "value", min: props.score ? 0 : undefined, max: props.score ? 1 : undefined, scale: !props.score },
    series: [{ name: props.label, type: "line", showSymbol: false, connectNulls: true, data: props.metrics.map((item) => item[props.valueKey]) }],
  }, true);
}
function resize() { chart?.resize(); }
onMounted(() => { if (root.value) { chart = init(root.value); render(); window.addEventListener("resize", resize); } });
watch(() => props.metrics, render, { deep: true });
onBeforeUnmount(() => { window.removeEventListener("resize", resize); chart?.dispose(); });
</script>
<template><div ref="root" class="metric-trend" role="img" :aria-label="`${label} 随 epoch 变化趋势`" /></template>
<style scoped>.metric-trend{width:100%;height:230px}</style>

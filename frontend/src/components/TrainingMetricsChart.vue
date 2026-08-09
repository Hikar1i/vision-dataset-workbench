<script setup lang="ts">
import type { TrainingMetric } from "../api/training";
import MetricTrendChart from "./MetricTrendChart.vue";
defineProps<{ metrics: TrainingMetric[] }>();
const charts = [
  { key: "box_loss", label: "box_loss", color: "#16866f", score: false },
  { key: "cls_loss", label: "cls_loss", color: "#d97706", score: false },
  { key: "dfl_loss", label: "dfl_loss", color: "#7c3aed", score: false },
  { key: "learning_rate", label: "learning_rate", color: "#2563eb", score: false },
  { key: "precision", label: "precision", color: "#dc2626", score: true },
  { key: "recall", label: "recall", color: "#0891b2", score: true },
] as const;
</script>
<template><div class="metrics-grid"><article v-for="chart in charts" :key="chart.key" class="metric-card"><header><strong>{{ chart.label }}</strong><span>{{ metrics.at(-1)?.[chart.key]?.toFixed(5) ?? '—' }}</span></header><MetricTrendChart :metrics="metrics" :value-key="chart.key" :label="chart.label" :color="chart.color" :score="chart.score" /></article></div></template>
<style scoped>.metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.metric-card{min-width:0;border:1px solid #e0e5eb;background:#fbfcfd}.metric-card header{display:flex;justify-content:space-between;padding:12px 14px 0}.metric-card header span{color:#687482;font:13px ui-monospace,monospace}@media(max-width:1100px){.metrics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.metrics-grid{grid-template-columns:1fr}}</style>

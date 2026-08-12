import type {
  TrainingModelDraft,
  TrainingResources,
  TrainingTaskDraft,
} from "../api/training";

export type TrainingDefaults = Pick<
  TrainingTaskDraft,
  | "default_dataset_export_id"
  | "default_dataset_mode"
  | "default_multi_dataset_config"
  | "default_template_id"
  | "default_base_model_id"
>;

export function effectiveResourceIds(
  row: TrainingModelDraft,
  defaults: TrainingDefaults,
) {
  return {
    datasetMode:
      row.dataset_mode === "inherit" ? defaults.default_dataset_mode : row.dataset_mode,
    datasetId:
      row.dataset_mode === "inherit"
        ? defaults.default_dataset_export_id
        : row.dataset_export_id,
    multiDatasetConfig:
      row.dataset_mode === "inherit"
        ? defaults.default_multi_dataset_config
        : row.multi_dataset_config,
    templateId: row.template_id || defaults.default_template_id,
    baseModelId: row.base_model_id || defaults.default_base_model_id,
  };
}

export function hasEffectiveResources(
  row: TrainingModelDraft,
  defaults: TrainingDefaults,
) {
  const value = effectiveResourceIds(row, defaults);
  const datasetReady =
    value.datasetMode === "multi"
      ? Boolean(
          value.multiDatasetConfig?.dataset_export_ids.length &&
            value.multiDatasetConfig.target_classes.length,
        )
      : Boolean(value.datasetId);
  return Boolean(datasetReady && value.templateId && value.baseModelId);
}

export function groupedOptions(
  items: { id: string; name: string; project_id: string; project_name: string }[],
) {
  const groups = new Map<string, { value: string; label: string; children: { value: string; label: string }[] }>();
  for (const item of items) {
    const group = groups.get(item.project_id) || {
      value: item.project_id,
      label: item.project_name,
      children: [],
    };
    group.children.push({ value: item.id, label: item.name });
    groups.set(item.project_id, group);
  }
  return [...groups.values()];
}

function safeBaseCode(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "yolo";
}

export function artifactPreview(
  row: TrainingModelDraft,
  defaults: TrainingDefaults,
  resources: TrainingResources,
  taskCode: string,
) {
  const ids = effectiveResourceIds(row, defaults);
  const template = resources.templates.find(({ id }) => id === ids.templateId);
  const base = resources.base_models.find(({ id }) => id === ids.baseModelId);
  if (!template || !base || !/^[a-z][a-z0-9-]{2,31}$/.test(taskCode)) return null;
  const day = new Date().toISOString().slice(2, 10).replaceAll("-", "");
  const epochs = row.epochs_override ?? template.epochs;
  const size = row.image_size_override ?? template.image_size;
  const mode = row.batch_mode_override ?? template.batch_mode;
  const value = row.batch_mode_override ? row.batch_value_override : template.batch_value;
  const batch = mode === "auto" ? "auto" : mode === "fraction" ? `${Math.round(Number(value) * 100)}pct` : String(Math.round(Number(value)));
  return `${taskCode}-${day}-g${row.gpu_index}-q${String(row.queue_order).padStart(2, "0")}-${safeBaseCode(base.model_code)}-s${size}-b${batch}-e${epochs}`;
}

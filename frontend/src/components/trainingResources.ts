import type {
  ExtraParametersOverride,
  TrainingModelDraft,
  TrainingResources,
  TrainingTaskDraft,
} from "../api/training";
import type { BatchMode, HyperparameterConfig } from "../api/hyperparameters";

export type TrainingDefaults = Pick<
  TrainingTaskDraft,
  | "default_dataset_export_id"
  | "default_dataset_mode"
  | "default_multi_dataset_config"
  | "default_template_id"
  | "default_epochs_override"
  | "default_batch_mode_override"
  | "default_batch_value_override"
  | "default_image_size_override"
  | "default_extra_parameters_override"
  | "default_base_model_id"
>;

export type TrainingHyperparameterOverrides = {
  epochs: number | null;
  batchMode: BatchMode | null;
  batchValue: number | null;
  imageSize: number | null;
  extra: ExtraParametersOverride | null;
};

export function templateConfig(
  template: TrainingResources["templates"][number],
): HyperparameterConfig {
  return {
    epochs: template.epochs,
    batch_mode: template.batch_mode,
    batch_value: template.batch_value,
    image_size: template.image_size,
    extra_parameters: { ...template.extra_parameters },
  };
}

export function applyHyperparameterOverrides(
  base: HyperparameterConfig,
  override: TrainingHyperparameterOverrides,
): HyperparameterConfig {
  const extra = { ...base.extra_parameters };
  for (const key of override.extra?.remove ?? []) delete extra[key];
  Object.assign(extra, override.extra?.set ?? {});
  return {
    epochs: override.epochs ?? base.epochs,
    batch_mode: override.batchMode ?? base.batch_mode,
    batch_value: override.batchMode == null ? base.batch_value : override.batchValue,
    image_size: override.imageSize ?? base.image_size,
    extra_parameters: extra,
  };
}

export function diffHyperparameterConfig(
  base: HyperparameterConfig,
  value: HyperparameterConfig,
): TrainingHyperparameterOverrides {
  const set: Record<string, unknown> = {};
  const remove: string[] = [];
  for (const key of new Set([
    ...Object.keys(base.extra_parameters),
    ...Object.keys(value.extra_parameters),
  ])) {
    if (!(key in value.extra_parameters)) remove.push(key);
    else if (JSON.stringify(value.extra_parameters[key]) !== JSON.stringify(base.extra_parameters[key]))
      set[key] = value.extra_parameters[key];
  }
  return {
    epochs: value.epochs === base.epochs ? null : value.epochs,
    batchMode:
      value.batch_mode === base.batch_mode && value.batch_value === base.batch_value
        ? null
        : value.batch_mode,
    batchValue:
      value.batch_mode === base.batch_mode && value.batch_value === base.batch_value
        ? null
        : value.batch_value,
    imageSize: value.image_size === base.image_size ? null : value.image_size,
    extra: Object.keys(set).length || remove.length ? { version: 1, set, remove } : null,
  };
}

export function hyperparameterOverrideCount(value: TrainingHyperparameterOverrides) {
  return [value.epochs, value.batchMode, value.imageSize].filter((item) => item != null).length
    + Object.keys(value.extra?.set ?? {}).length
    + (value.extra?.remove.length ?? 0);
}

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
  const override = row.template_id
    ? {
        epochs: row.epochs_override,
        batchMode: row.batch_mode_override,
        batchValue: row.batch_value_override,
        imageSize: row.image_size_override,
        extra: row.extra_parameters_override,
      }
    : {
        epochs: defaults.default_epochs_override,
        batchMode: defaults.default_batch_mode_override,
        batchValue: defaults.default_batch_value_override,
        imageSize: defaults.default_image_size_override,
        extra: defaults.default_extra_parameters_override,
      };
  const parameters = applyHyperparameterOverrides(templateConfig(template), override);
  const epochs = parameters.epochs;
  const size = parameters.image_size;
  const mode = parameters.batch_mode;
  const value = parameters.batch_value;
  const batch = mode === "auto" ? "auto" : mode === "fraction" ? `${Math.round(Number(value) * 100)}pct` : String(Math.round(Number(value)));
  return `${taskCode}-${day}-g${row.gpu_index}-q${String(row.queue_order).padStart(2, "0")}-${safeBaseCode(base.model_code)}-s${size}-b${batch}-e${epochs}`;
}

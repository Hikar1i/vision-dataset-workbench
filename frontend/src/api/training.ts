import { json } from "./auth";

export type TrainingStatus =
  | "draft"
  | "queued"
  | "running"
  | "canceling"
  | "canceled"
  | "start_failed"
  | "failed"
  | "partial"
  | "succeeded";
export type TrainingMode =
  "single_model" | "single_device_serial" | "custom_sequence";
export type RunStatus =
  | "queued"
  | "running"
  | "canceling"
  | "canceled"
  | "start_failed"
  | "failed"
  | "succeeded";

export type TrainingMetric = {
  epoch: number;
  box_loss: number | null;
  cls_loss: number | null;
  dfl_loss: number | null;
  learning_rate: number | null;
  precision: number | null;
  recall: number | null;
  map50: number | null;
  map50_95: number | null;
};
export type TrainingRun = {
  id: string;
  attempt_no: number;
  kind: "initial" | "retry" | "resume" | "extend";
  status: RunStatus;
  gpu_index: number;
  pid: number | null;
  current_epoch: number;
  target_epochs: number;
  progress: number;
  best_path: string | null;
  last_path: string | null;
  host_snapshot: Record<string, unknown>;
  error: string | null;
  warning: string | null;
  enqueued_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type ActionAvailability = {
  allowed: boolean;
  reason_code: string | null;
  message: string | null;
};
export type TrainingModel = {
  id: string;
  training_task_id: string;
  name: string;
  description: string;
  artifact_code: string | null;
  dataset_export_id: string | null;
  template_id: string | null;
  base_model_id: string | null;
  epochs_override: number | null;
  batch_mode_override: "auto" | "fixed" | "fraction" | null;
  batch_value_override: number | null;
  image_size_override: number | null;
  gpu_index: number;
  queue_order: number;
  status: RunStatus | "draft";
  progress: number;
  derived_from_id: string | null;
  continuation_of_id: string | null;
  continuation_checkpoint: string | null;
  dataset_snapshot: Record<string, unknown>;
  template_snapshot: Record<string, unknown>;
  base_model_snapshot: Record<string, unknown>;
  actions: Record<string, ActionAvailability>;
  runs: TrainingRun[];
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type TrainingTask = {
  id: string;
  code: string;
  name: string;
  description: string;
  status: TrainingStatus;
  mode: TrainingMode;
  progress: number;
  model_count: number;
  default_dataset_export_id: string | null;
  default_template_id: string | null;
  default_base_model_id: string | null;
  created_by_id: string;
  can_manage: boolean;
  version: number;
  submitted_at: string | null;
  last_run_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  actions: Record<string, ActionAvailability>;
  models?: TrainingModel[];
};
export type GpuDevice = {
  index: number;
  name: string;
  memory_total_mb: number;
  memory_used_mb: number;
  memory_percent: number;
  utilization_percent: number;
  level: "green" | "orange" | "red";
};
export type TrainingCapabilities = {
  available: boolean;
  reason: string | null;
  training_available: boolean;
  training_reason: string | null;
  devices: GpuDevice[];
  host: Record<string, unknown>;
};
export type TrainingResources = {
  datasets: { id: string; name: string; project_id: string; project_name: string }[];
  templates: {
    id: string;
    name: string;
    epochs: number;
    batch_mode: string;
    batch_value: number | null;
    image_size: number;
  }[];
  base_models: {
    id: string;
    name: string;
    model_code: string;
    project_id: string;
    project_name: string;
  }[];
};
export type TrainingModelDraft = {
  name: string;
  description: string;
  dataset_export_id: string | null;
  template_id: string | null;
  base_model_id: string | null;
  epochs_override: number | null;
  batch_mode_override: "auto" | "fixed" | "fraction" | null;
  batch_value_override: number | null;
  image_size_override: number | null;
  gpu_index: number;
  queue_order: number;
};
export type TrainingTaskDraft = {
  code: string;
  name: string;
  description: string;
  mode: TrainingMode;
  default_dataset_export_id: string | null;
  default_template_id: string | null;
  default_base_model_id: string | null;
  models: TrainingModelDraft[];
};

export const getTrainingCapabilities = () =>
  json<TrainingCapabilities>("/api/v1/training/capabilities");
export const getTrainingResources = () =>
  json<TrainingResources>("/api/v1/training/resources");
export const listTrainingTasks = () =>
  json<TrainingTask[]>("/api/v1/training-tasks");
export const getTrainingTask = (id: string) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}`);
export const createTrainingTask = (payload: TrainingTaskDraft) =>
  json<TrainingTask>("/api/v1/training-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const updateTrainingTask = (
  id: string,
  version: number,
  payload: Omit<TrainingTaskDraft, "code">,
) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, version }),
  });
export const startTrainingTask = (id: string) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}/start`, { method: "POST" });
export const cancelTrainingTask = (id: string) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}/cancel`, { method: "POST" });
export const retryFailedTrainingModels = (id: string) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}/retry-failed`, {
    method: "POST",
  });
export const resumeInterruptedTrainingModels = (id: string) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}/resume-interrupted`, { method: "POST" });
export const deriveTrainingTask = (
  id: string,
  payload: { task_code: string; task_name: string; description: string },
) =>
  json<TrainingTask>(`/api/v1/training-tasks/${id}/derive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const deleteTrainingTask = (id: string) =>
  json<void>(`/api/v1/training-tasks/${id}`, { method: "DELETE" });
export const cancelTrainingModel = (id: string) =>
  json<void>(`/api/v1/training-models/${id}/cancel`, { method: "POST" });
export const deleteTrainingModel = (
  id: string,
  confirmPublishedModel = false,
) =>
  json<void>(
    `/api/v1/training-models/${id}?confirm_published_model=${confirmPublishedModel}`,
    { method: "DELETE" },
  );
export const retryTrainingModel = (id: string, confirmReplace = false) =>
  json<TrainingRun>(`/api/v1/training-models/${id}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_replace: confirmReplace }),
  });
export const resumeTrainingModel = (id: string) =>
  json<TrainingRun>(`/api/v1/training-models/${id}/resume`, { method: "POST" });
export const deriveTrainingModel = (
  id: string,
  payload: Record<string, unknown>,
) =>
  json<TrainingTask>(`/api/v1/training-models/${id}/derive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const extendTrainingModel = (
  id: string,
  payload: Record<string, unknown>,
) =>
  json<TrainingTask>(`/api/v1/training-models/${id}/extend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const getTrainingMetrics = (runId: string, afterEpoch = 0) =>
  json<TrainingMetric[]>(
    `/api/v1/training-runs/${runId}/metrics?after_epoch=${afterEpoch}`,
  );
export const getTrainingLog = (runId: string, cursor = 0) =>
  json<{ content: string; next_cursor: number }>(
    `/api/v1/training-runs/${runId}/log?cursor=${cursor}`,
  );
export type PrCurve =
  | {
      version: number;
      kind: "interactive";
      series: { name: string; points: [number, number][] }[];
    }
  | { version: number; kind: "unavailable"; series: [] };
export const getTrainingPrCurve = (runId: string) =>
  json<PrCurve>(`/api/v1/training-runs/${runId}/pr-curve`);

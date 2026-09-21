import type { MultiDatasetConfig, TrainingResources } from "../api/training";

export type DatasetResource = TrainingResources["datasets"][number];
export type MappingDraft = {
  selected: string[];
  order: string[];
  deleted: string[];
};

export function availableClasses(selected: string[], datasets: DatasetResource[]) {
  const result: string[] = [];
  for (const id of selected) {
    const dataset = datasets.find((item) => item.id === id);
    for (const label of dataset?.labels ?? []) {
      const name = label.name.trim();
      if (name && !result.includes(name)) result.push(name);
    }
  }
  return result;
}

export function mappingDraft(
  config: MultiDatasetConfig | null,
  datasets: DatasetResource[],
): MappingDraft {
  const selected = (config?.dataset_export_ids ?? []).filter((id) =>
    datasets.some((item) => item.id === id),
  );
  const available = availableClasses(selected, datasets);
  const order = (config?.target_classes ?? []).filter((name) => available.includes(name));
  for (const name of available) if (!order.includes(name)) order.push(name);
  return { selected, order, deleted: [] };
}

export function syncMapping(draft: MappingDraft, datasets: DatasetResource[]) {
  const available = availableClasses(draft.selected, datasets);
  draft.order = draft.order.filter(
    (name) => available.includes(name) && !draft.deleted.includes(name),
  );
  for (const name of available)
    if (!draft.order.includes(name) && !draft.deleted.includes(name)) draft.order.push(name);
  draft.deleted = draft.deleted.filter((name) => available.includes(name));
}

export function moveTarget(draft: MappingDraft, index: number, delta: -1 | 1) {
  const target = index + delta;
  if (target < 0 || target >= draft.order.length) return;
  [draft.order[index], draft.order[target]] = [draft.order[target]!, draft.order[index]!];
}

export function deleteTarget(draft: MappingDraft, name: string) {
  draft.order = draft.order.filter((item) => item !== name);
  if (!draft.deleted.includes(name)) draft.deleted.push(name);
}

export function restoreTargets(draft: MappingDraft, datasets: DatasetResource[]) {
  const available = availableClasses(draft.selected, datasets);
  for (const name of draft.deleted)
    if (available.includes(name) && !draft.order.includes(name)) draft.order.push(name);
  draft.deleted = [];
}

export function canonicalMapping(draft: MappingDraft): MultiDatasetConfig {
  return {
    version: 1,
    dataset_export_ids: [...draft.selected],
    target_classes: [...draft.order],
  };
}

export function mappingValid(draft: MappingDraft) {
  return draft.selected.length > 0 && draft.order.length > 0;
}

export function targetSources(
  name: string,
  selected: string[],
  datasets: DatasetResource[],
) {
  return selected.flatMap((id) => {
    const dataset = datasets.find((item) => item.id === id);
    return (dataset?.labels ?? [])
      .filter((label) => label.name.trim() === name)
      .map((label) => ({
        dataset: dataset!.name,
        project: dataset!.project_name,
        index: label.index,
        name,
      }));
  });
}

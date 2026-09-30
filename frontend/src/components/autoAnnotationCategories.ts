export type CategoryLabel = { name: string; enabled: boolean }
export type CategoryResolution = { categories: string[]; error: string }

const uniqueNames = (values: string[]) => [...new Set(
  values.map((value) => value.trim().toLowerCase()).filter(Boolean),
)]

export function resolveAutoAnnotationCategories(
  selected: string[],
  query: string,
  labels: CategoryLabel[],
): CategoryResolution {
  const pending = query.trim().toLowerCase()
  const values = pending
    ? [...selected.filter((value) => value !== '__all__'), pending]
    : selected
  if (values.includes('__all__')) {
    const categories = uniqueNames(
      labels.filter((label) => label.enabled).map((label) => label.name),
    )
    return categories.length
      ? { categories, error: '' }
      : { categories: [], error: '本项目暂无启用类别，请先新增或启用类别。' }
  }
  const categories = uniqueNames(values)
  return categories.length
    ? { categories, error: '' }
    : { categories: [], error: '请选择或输入至少一个类别。' }
}

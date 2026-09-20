import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readView = (name: string) => readFileSync(resolve(`src/views/${name}.vue`), 'utf8')

describe('date-time presentation', () => {
  it('uses the shared two-line component in every requested list', () => {
    const projects = readView('ProjectsView')
    const datasets = readView('ProjectDatasetsView')
    const modelProjects = readView('ModelProjectsView')
    const models = readView('ModelProjectDetailView')
    const templates = readView('HyperparameterTemplatesView')
    const tasks = readView('TrainingTasksView')

    expect(projects).toContain('<VDateTime :value="project.updated_at" />')
    expect(datasets).toContain('<VDateTime :value="row.completed_at || row.created_at" />')
    expect(modelProjects).toContain('<VDateTime :value="project.created_at" />')
    expect(modelProjects).toContain('<VDateTime :value="project.updated_at" />')
    expect(models).toContain('<VDateTime :value="model.updated_at" />')
    expect(templates).toContain('<VDateTime :value="item.updated_at" />')
    expect(tasks).toContain('<VDateTime :value="task.created_at" />')
    expect(tasks).toContain('<VDateTime v-if="task.last_run_at" :value="task.last_run_at" />')

    expect(datasets).not.toContain('new Date(value).toLocaleString()')
    expect(tasks).not.toContain('const stamp =')
  })

  it('keeps list date columns compact', () => {
    expect(readView('ProjectsView')).toContain('110px 150px')
    expect(readView('ProjectDatasetsView')).toContain('label="导出时间" width="100"')
    expect(readView('ModelProjectsView')).toContain('106px 106px 148px')
    expect(readView('ModelProjectDetailView')).toContain('106px 350px')
    expect(readView('HyperparameterTemplatesView')).toContain('110px 290px')
    expect(readView('TrainingTasksView')).toContain('110px 110px minmax(390px, 2fr)')
  })

  it('uses the full shared formatter in requested detail views', () => {
    const hyperparameters = readView('HyperparameterTemplateDetailView')
    const trainingModel = readView('TrainingModelDetailView')

    expect(hyperparameters).toContain('formatDateTime(item.created_at)')
    expect(hyperparameters).toContain('formatDateTime(item.updated_at)')
    expect(trainingModel).toContain('formatDateTime(value.created_at)')
    expect(trainingModel).toContain('formatDateTime(value.started_at)')
    expect(trainingModel).toContain('formatDateTime(value.finished_at)')
    expect(trainingModel).not.toContain('function formatTime(')
  })
})

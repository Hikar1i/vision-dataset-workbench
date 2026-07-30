import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'

import { getProject } from '../api/projects'
import ProjectLayout from './ProjectLayout.vue'

vi.mock('../api/projects', () => ({
  getProject: vi.fn().mockResolvedValue({
    id: 'project-1',
    name: 'Smoke Dataset',
    role: 'owner',
  }),
}))

it('loads project context and renders only implemented tabs', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/projects/:id',
        component: ProjectLayout,
        children: [
          { path: 'videos', component: { template: '<div>videos</div>' } },
          { path: 'labels', component: { template: '<div>labels</div>' } },
          { path: 'datasets', component: { template: '<div>datasets</div>' } },
          { path: 'settings', component: { template: '<div>settings</div>' } },
        ],
      },
    ],
  })
  await router.push('/projects/project-1/videos')
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
  await flushPromises()

  expect(getProject).toHaveBeenCalledWith('project-1')
  expect(wrapper.get('[data-test="project-context"]').text()).toContain('Smoke Dataset')
  expect(wrapper.get('[data-test="project-tab-videos"]').attributes('href')).toBe(
    '/projects/project-1/videos',
  )
  expect(wrapper.get('[data-test="project-tab-labels"]').attributes('href')).toBe(
    '/projects/project-1/labels',
  )
  expect(wrapper.get('[data-test="project-tab-datasets"]').attributes('href')).toBe(
    '/projects/project-1/datasets',
  )
})

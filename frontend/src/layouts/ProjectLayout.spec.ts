import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, onMounted } from 'vue'
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

it('does not remount the video page for its annotation child route', async () => {
  let mounts = 0
  const Videos = defineComponent({
    setup() { onMounted(() => { mounts += 1 }) },
    template: '<main data-test="videos-host"><RouterView /></main>',
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/projects/:id',
      component: ProjectLayout,
      children: [{
        path: 'videos',
        name: 'project-videos',
        component: Videos,
        children: [{
          path: ':videoId/annotation',
          name: 'video-annotation',
          component: { template: '<div data-test="annotation-child" />' },
        }],
      }],
    }],
  })
  await router.push('/projects/project-1/videos')
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
  await flushPromises()
  const host = wrapper.get('[data-test="videos-host"]').element

  await router.push('/projects/project-1/videos/video-1/annotation')
  await flushPromises()

  expect(mounts).toBe(1)
  expect(wrapper.get('[data-test="videos-host"]').element).toBe(host)
  expect(wrapper.find('[data-test="annotation-child"]').exists()).toBe(true)
})

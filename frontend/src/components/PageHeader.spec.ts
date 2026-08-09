import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

import PageHeader from './PageHeader.vue'

describe('PageHeader', () => {
  it('renders back navigation, title, metadata, actions, stats, and tabs', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/model-projects/:id', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(PageHeader, {
      props: {
        title: '模型详情',
        backTo: '/model-projects/p1',
        backLabel: '返回模型列表',
      },
      slots: {
        meta: '<span data-test="meta">3 个可用</span>',
        actions: '<button data-test="action">导入模型</button>',
        stats: '<span data-test="stats">共 8 个模型</span>',
        tabs: '<a data-test="tab">配置列表</a>',
      },
      global: { plugins: [router], stubs: { 'el-icon': true } },
    })

    expect(wrapper.get('h1').text()).toBe('模型详情')
    expect(wrapper.get('[aria-label="返回模型列表"]').attributes('href')).toBe('/model-projects/p1')
    expect(wrapper.get('[data-test="meta"]').text()).toBe('3 个可用')
    expect(wrapper.get('[data-test="action"]').text()).toBe('导入模型')
    expect(wrapper.get('[data-test="stats"]').text()).toBe('共 8 个模型')
    expect(wrapper.get('nav[aria-label="页面子导航"]').text()).toBe('配置列表')
  })

  it('omits optional regions when no slot is supplied', () => {
    const wrapper = mount(PageHeader, { props: { title: 'Overview' } })

    expect(wrapper.find('.page-header__back').exists()).toBe(false)
    expect(wrapper.find('.page-header__stats').exists()).toBe(false)
    expect(wrapper.find('.page-header__tabs').exists()).toBe(false)
  })
})

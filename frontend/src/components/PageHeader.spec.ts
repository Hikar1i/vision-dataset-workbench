import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

import PageHeader from './PageHeader.vue'

const router = () => {
  const instance = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/model-projects/:id', component: { template: '<div />' } },
    ],
  })
  return instance
}

describe('PageHeader', () => {
  it('renders back navigation, eyebrow, title, metadata, actions, and tabs', async () => {
    const instance = router()
    await instance.push('/')
    await instance.isReady()

    const wrapper = mount(PageHeader, {
      props: {
        title: '模型详情',
        kind: 'model',
        code: 'A82EE1',
        backTo: '/model-projects/p1',
        backLabel: '返回模型列表',
      },
      slots: {
        meta: '<span data-test="meta">3 个可用</span>',
        actions: '<button data-test="action">导入模型</button>',
        tabs: '<a data-test="tab">配置列表</a>',
      },
      global: { plugins: [instance], stubs: { 'el-icon': true } },
    })

    expect(wrapper.get('h1').text()).toBe('模型详情')
    expect(wrapper.get('[aria-label="返回模型列表"]').attributes('href')).toBe('/model-projects/p1')
    expect(wrapper.get('[data-test="meta"]').text()).toBe('3 个可用')
    expect(wrapper.get('[data-test="action"]').text()).toBe('导入模型')
    expect(wrapper.get('nav[aria-label="页面子导航"]').text()).toBe('配置列表')
  })

  it('puts the resource kind and short code in the eyebrow above the title', async () => {
    const instance = router()
    await instance.push('/')
    await instance.isReady()

    const wrapper = mount(PageHeader, {
      props: { title: 'fire-det', kind: 'project', code: '128E0B' },
      global: { plugins: [instance], stubs: { 'el-icon': true } },
    })

    const eyebrow = wrapper.get('.page-header__eyebrow').text()
    expect(eyebrow).toContain('project')
    expect(eyebrow).toContain('128E0B')
    // 对象名称是 h1，不再和身份信息挤在同一行
    expect(wrapper.get('h1').text()).toBe('fire-det')
  })

  it('keeps the fixed-height regions rendered so header geometry never shifts', () => {
    // eyebrow / 副信息 / 末行都定高且常驻：用 v-if 省掉空段会让"有权限标签的
    // 项目页"比"没有的列表页"高几像素，标题与正文起点随页面漂移。
    const wrapper = mount(PageHeader, { props: { title: 'Overview' } })

    expect(wrapper.find('.page-header__back').exists()).toBe(false)
    expect(wrapper.find('.page-header__eyebrow').exists()).toBe(true)
    expect(wrapper.find('.page-header__meta').exists()).toBe(true)
    expect(wrapper.find('.page-header__bar').exists()).toBe(true)
    expect(wrapper.find('.page-header__tabs').exists()).toBe(true)
    // 空段不得渲染出可读内容，否则会出现看不见的占位文字
    expect(wrapper.get('.page-header__eyebrow').text()).toBe('')
    expect(wrapper.get('.page-header__meta').text()).toBe('')
  })
})

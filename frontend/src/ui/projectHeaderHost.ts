import { inject, provide } from 'vue'

/**
 * 数据集项目子页把统计与操作 Teleport 进 ProjectLayout 的唯一头部。
 *
 * 当子页被单独挂载（单元测试直接 mount 子页，不经过 ProjectLayout）时宿主并不存在，
 * Teleport 会因找不到目标而报错。这里由 ProjectLayout 显式声明宿主存在；
 * 未声明时 Teleport 以 disabled 方式就地渲染，行为和结构断言都保持不变。
 */
const HOST = Symbol('vdw-project-header-host')

export function provideProjectHeaderHost() {
  provide(HOST, true)
}

export function useProjectHeaderHost() {
  return inject(HOST, false)
}

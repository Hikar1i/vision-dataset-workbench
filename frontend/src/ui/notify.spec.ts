import { ElNotification } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { notify } from './notify'

afterEach(() => vi.restoreAllMocks())

describe('notify', () => {
  it('shows successful actions at the top right', () => {
    const success = vi.spyOn(ElNotification, 'success').mockReturnValue({ close: vi.fn() } as never)

    notify.success('配置已保存')

    expect(success).toHaveBeenCalledWith({
      title: '操作成功',
      message: '配置已保存',
      position: 'top-right',
      duration: 4500,
    })
  })

  it('keeps errors visible longer than warnings and information', () => {
    const error = vi.spyOn(ElNotification, 'error').mockReturnValue({ close: vi.fn() } as never)
    const warning = vi.spyOn(ElNotification, 'warning').mockReturnValue({ close: vi.fn() } as never)
    const info = vi.spyOn(ElNotification, 'info').mockReturnValue({ close: vi.fn() } as never)

    notify.error('连接失败')
    notify.warning('请检查配置')
    notify.info('筛选条件已更新')

    expect(error).toHaveBeenCalledWith(expect.objectContaining({
      title: '操作失败', position: 'top-right', duration: 8000,
    }))
    expect(warning).toHaveBeenCalledWith(expect.objectContaining({
      title: '请注意', position: 'top-right', duration: 6000,
    }))
    expect(info).toHaveBeenCalledWith(expect.objectContaining({
      title: '提示', position: 'top-right', duration: 4500,
    }))
  })
})

import { ElNotification } from 'element-plus'

export const notify = {
  success(message: string) {
    return ElNotification.success({
      title: '操作成功', message, position: 'top-right', duration: 4500,
    })
  },
  error(message: string) {
    return ElNotification.error({
      title: '操作失败', message, position: 'top-right', duration: 8000,
    })
  },
  warning(message: string) {
    return ElNotification.warning({
      title: '请注意', message, position: 'top-right', duration: 6000,
    })
  },
  info(message: string) {
    return ElNotification.info({
      title: '提示', message, position: 'top-right', duration: 4500,
    })
  },
}

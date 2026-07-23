export type SetupStatus = { initialized: boolean }

export async function getSetupStatus(): Promise<SetupStatus> {
  const response = await fetch('/api/v1/setup/status')
  if (!response.ok) throw new Error('无法读取初始化状态')
  return response.json()
}

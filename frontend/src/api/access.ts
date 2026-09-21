export type Permission =
  | 'project.read'
  | 'project.update'
  | 'project.members.manage'
  | 'project.delete'
  | 'artifact.read'
  | 'artifact.download'
  | 'artifact.consume'
  | 'task.read'
  | 'task.execute'

export type ProjectRole = 'owner' | 'editor' | 'viewer'

export type ResourceAccess = {
  role: ProjectRole | null
  source: 'system_admin' | 'owner' | 'membership' | 'system_resource'
  permissions: Permission[]
}

export const can = (access: ResourceAccess | undefined, permission: Permission) =>
  Boolean(access?.permissions.includes(permission))

export const accessLabel = (access: ResourceAccess) =>
  access.source === 'system_admin'
    ? '管理员'
    : access.role === 'owner'
      ? '所有者'
      : access.role === 'editor'
        ? '编辑者'
        : '只读'

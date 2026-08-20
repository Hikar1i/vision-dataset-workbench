export type VideoListState = { page: number; pageSize: number }

const videoListStates = new Map<string, VideoListState>()
const frameGridScales = new Map<string, number>()

function frameScope(projectId: string, videoId: string) {
  return `${projectId}:${videoId}`
}

export function readVideoListState(projectId: string): VideoListState {
  return { ...(videoListStates.get(projectId) ?? { page: 1, pageSize: 50 }) }
}

export function saveVideoListState(projectId: string, state: VideoListState) {
  videoListStates.set(projectId, { ...state })
}

export function readFrameGridScale(projectId: string, videoId: string) {
  return frameGridScales.get(frameScope(projectId, videoId)) ?? 1
}

export function saveFrameGridScale(projectId: string, videoId: string, scale: number) {
  frameGridScales.set(frameScope(projectId, videoId), scale)
}

export function clearVideoWorkspaceState() {
  videoListStates.clear()
  frameGridScales.clear()
}

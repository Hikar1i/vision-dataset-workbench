# Annotation and Frame Detail Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 统一标注与筛帧工作台的标注标题、缩略图、标题栏和按钮反馈，并让筛帧缩略图默认展示标注框。

**Architecture:** 扩展既有 `FrameAnnotationThumbnail` 作为三处缩略图的唯一展示组件，复用帧列表 `include_annotations=true` 批量返回标注预览。完整画布继续消费既有 `FrameAnnotation.source/confidence`，只改变渲染文本与位置；筛帧开关仅为组件内存状态。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Konva、Vitest、Vite

---

### Task 1: 统一缩略图展示

**Files:**
- Create: `frontend/src/components/framePresentation.ts`
- Modify: `frontend/src/components/FrameAnnotationThumbnail.vue`
- Modify: `frontend/src/components/FrameAnnotationThumbnail.spec.ts`
- Modify: `frontend/src/views/AnnotationWorkbenchView.vue`

- [x] **Step 1: 写失败测试**

在 `FrameAnnotationThumbnail.spec.ts` 增加启用、停用和累计分钟断言：

```ts
expect(wrapper.get('.timestamp').text()).toBe('65:02.462')
expect(wrapper.get('.frame-status').text()).toBe('已启用')
await wrapper.setProps({ disabled: true })
expect(wrapper.get('.frame-status').text()).toBe('已停用')
expect(wrapper.classes()).toContain('disabled')
```

- [x] **Step 2: 验证测试失败**

Run: `cd frontend && npm test -- --run src/components/FrameAnnotationThumbnail.spec.ts`  
Expected: FAIL，缺少 `timestamp` 或 `frame-status`。

- [x] **Step 3: 实现统一时间与状态**

在 `framePresentation.ts` 使用毫秒整数避免秒数进位产生 `60.000`：

```ts
export function formatFrameTimestamp(seconds: number) {
  const milliseconds = Math.max(0, Math.round(seconds * 1000))
  const minutes = Math.floor(milliseconds / 60_000)
  const remainder = ((milliseconds % 60_000) / 1000).toFixed(3).padStart(6, '0')
  return `${minutes}:${remainder}`
}
```

为 `FrameAnnotationThumbnail` 增加 `timeOffset`，固定渲染右上时间、右下序号和左下启停状态；停用遮罩保持不变。`AnnotationWorkbenchView.vue` 两处调用传入 `frame.time_offset`，删除网格外层重复的 `.frame-time`。

- [x] **Step 4: 验证测试通过**

Run: `cd frontend && npm test -- --run src/components/FrameAnnotationThumbnail.spec.ts src/views/AnnotationWorkbenchView.spec.ts`  
Expected: PASS。

### Task 2: 调整标注画布标题和主操作按钮

**Files:**
- Modify: `frontend/src/components/AnnotationCanvas.vue`
- Modify: `frontend/src/components/AnnotationCanvas.spec.ts`
- Modify: `frontend/src/views/AnnotationWorkbenchView.vue`
- Modify: `frontend/src/layouts/FocusLayout.vue`
- Modify: `frontend/src/layouts/FocusLayout.spec.ts`

- [x] **Step 1: 写失败测试**

把第二个测试标注改为模型来源并断言标题与框外坐标：

```ts
source: 'model',
confidence: 0.9,
// ...
expect(labels.map((item) => item.text())).toEqual(['helmet #1', 'person #2 · 0.90'])
expect(labelGroups[0]?.props('config').y).toBe(-6) // y_min 20 - 26
```

同步把 `FocusLayout.spec.ts` 品牌断言改为 `VDM / ANNOTATION`，保留用户已修改的模板。

- [x] **Step 2: 验证测试失败**

Run: `cd frontend && npm test -- --run src/components/AnnotationCanvas.spec.ts src/layouts/FocusLayout.spec.ts`  
Expected: AnnotationCanvas 标题或位置断言 FAIL。

- [x] **Step 3: 实现框外标题和主按钮样式**

修改标题函数：

```ts
function annotationTitle(item: FrameAnnotation) {
  const base = `${labelMap.value.get(item.label_id)?.name ?? 'unknown'} #${annotationOrder.value.get(item.id)}`
  return item.source === 'model' && item.confidence !== null
    ? `${base} · ${item.confidence.toFixed(2)}`
    : base
}
```

标题组改为 `{ x: item.x_min, y: item.y_min - 26, listening: false }`。给“标注统计”“单张运行”“批量运行”增加同一个 `primary-action` 类，使用筛帧保存按钮的 `#16866f` 背景和边框，并保留禁用态。

- [x] **Step 4: 验证测试通过**

Run: `cd frontend && npm test -- --run src/components/AnnotationCanvas.spec.ts src/layouts/FocusLayout.spec.ts src/views/AnnotationWorkbenchView.spec.ts`  
Expected: PASS。

### Task 3: 筛帧缩略标注与稳定交互

**Files:**
- Modify: `frontend/src/components/FramesDialog.vue`
- Modify: `frontend/src/components/FramesDialog.spec.ts`

- [x] **Step 1: 写失败测试**

让帧列表 mock 在首帧返回 `annotations`，并断言：

```ts
expect(fetch.mock.calls.some(([url]) => String(url).includes('include_annotations=true'))).toBe(true)
expect(wrapper.get('[data-test="thumbnail-annotations-switch"]').attributes('modelvalue')).toBe('true')
expect(wrapper.findAll('[data-test="frame-card"] .annotation-preview rect')).toHaveLength(1)
await wrapper.get('[data-test="thumbnail-annotations-switch"]').trigger('click')
expect(wrapper.find('[data-test="frame-card"] .annotation-preview').exists()).toBe(false)
```

把大图 mock 标注改为模型来源，并断言 `helmet #1 · 0.91`；断言筛帧品牌为 `VDM / FRAMES`。

- [x] **Step 2: 验证测试失败**

Run: `cd frontend && npm test -- --run src/components/FramesDialog.spec.ts`  
Expected: FAIL，缺少开关、批量标注参数和大图置信度标题。

- [x] **Step 3: 实现最小改动**

- `listFrames` 的首批和后续分页传入 `includeAnnotations=true`。
- 增加 `const showThumbnailAnnotations = ref(true)`，不在打开/关闭对话框时重置。
- 工具栏增加默认开启的“缩略图标注”开关。
- 网格用 `FrameAnnotationThumbnail` 渲染图片、时间、序号、启停状态和可选标注框；范围选择框仍由筛帧页面叠加。
- 大图标题使用 `{类别} #{顺序}`，仅模型标注追加两位置信度；标题组 y 坐标减去自身高度并允许 SVG overflow。
- 标题文案改为 `VDM / FRAMES` 并对齐焦点页样式。
- 筛帧范围内覆盖全局按钮和卡片 hover/active 位移，保留颜色、边框和阴影变化。

- [x] **Step 4: 验证测试通过**

Run: `cd frontend && npm test -- --run src/components/FramesDialog.spec.ts`  
Expected: PASS。

### Task 4: 文档、全量验证与提交

**Files:**
- Modify: `docs/05-code-style.md`
- Modify: `docs/06-testing-strategy.md`
- Move: `docs/plans/2026-07-28-annotation-frame-detail-polish-implementation.md` → `docs/plans/completed/2026-07-28-annotation-frame-detail-polish-implementation.md`

- [x] **Step 1: 更新规范**

记录框外标题、模型置信度、统一 `m:ss.SSS` 缩略图、默认开启的内存开关和筛帧工作台禁用位置位移动效；测试文档补充对应组件覆盖。

- [x] **Step 2: 运行完整验证**

Run: `cd frontend && npm test`  
Expected: 所有 Vitest 测试 PASS。

Run: `cd frontend && npm run build`  
Expected: `vue-tsc -b` 和 Vite 生产构建成功；既有 chunk-size warning 可接受。

Run: `git diff --check`  
Expected: 无空白错误。

- [x] **Step 3: 移动已完成计划并提交**

```bash
mkdir -p docs/plans/completed
git add frontend/src docs/05-code-style.md docs/06-testing-strategy.md docs/plans
git commit -m "feat: 统一标注与筛帧工作台展示细节"
```

提交包含用户已授权的 `FocusLayout.vue` 品牌文案修改。

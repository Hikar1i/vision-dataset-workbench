# Annotation Frame Grid Overflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 防止标注工作台全部采样帧网格在帧数较多时压缩卡片并裁掉底部状态。

**Architecture:** 保留现有覆盖层和原生滚动，只在网格与直接子卡片上补足尺寸约束。测试锁定专用卡片类，文档记录网格不得为了单屏容纳全部帧而压缩。

**Tech Stack:** Vue 3、CSS Grid、Vitest、Vite

---

### Task 1: 固定全部帧网格卡片比例

**Files:**
- Modify: `frontend/src/views/AnnotationWorkbenchView.vue`
- Modify: `frontend/src/views/AnnotationWorkbenchView.spec.ts`
- Modify: `docs/05-code-style.md`
- Move: `docs/plans/2026-07-29-annotation-frame-grid-overflow-implementation.md` → `docs/plans/completed/2026-07-29-annotation-frame-grid-overflow-implementation.md`

- [ ] **Step 1: 写失败测试**

在现有工作台组件测试中打开全部采样帧，并锁定网格与卡片专用类：

```ts
await wrapper.get('[title="展开全部采样帧"]').trigger('click')
expect(wrapper.get('[data-test="frame-grid"]').classes()).toContain('frame-grid')
expect(wrapper.findAll('[data-test="frame-grid-card"]')).toHaveLength(2)
```

- [ ] **Step 2: 验证测试失败**

Run: `cd frontend && npm test -- --run src/views/AnnotationWorkbenchView.spec.ts`  
Expected: FAIL，缺少 `frame-grid` 或 `frame-grid-card` 测试标记。

- [ ] **Step 3: 实现最小 CSS 修复**

模板为网格和直接子按钮增加测试标记；CSS 使用现有滚动容器：

```css
.frame-grid {
  min-height: 0;
  grid-auto-rows: max-content;
}

.frame-grid-card {
  aspect-ratio: 16 / 9;
  align-self: start;
}
```

不改变帧数据加载、列宽、覆盖层标题、缩略图组件或点击切帧逻辑。

- [ ] **Step 4: 更新规范**

在 `docs/05-code-style.md` 的在线标注工作台规范中注明：全部帧网格卡片固定16:9，内容超出时纵向滚动，禁止压缩网格行。

- [ ] **Step 5: 完整验证**

Run: `cd frontend && npm test`  
Expected: 全部 Vitest 测试 PASS。

Run: `cd frontend && npm run build`  
Expected: TypeScript 与 Vite 构建成功；既有 chunk-size warning 可接受。

Run: `git diff --check`  
Expected: 无空白错误。

- [ ] **Step 6: 归档并提交**

```bash
mkdir -p docs/plans/completed
git add frontend/src/views/AnnotationWorkbenchView.vue frontend/src/views/AnnotationWorkbenchView.spec.ts docs/05-code-style.md docs/plans
git commit -m "fix: 修复全部采样帧网格压缩"
```


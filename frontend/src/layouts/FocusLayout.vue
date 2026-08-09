<template>
  <section class="focus-layout" data-theme="focus">
    <header class="focus-header">
      <strong data-test="focus-brand">VDM / ANNOTATION</strong>
      <div id="focus-header-tools" class="focus-header-tools" />
    </header>
    <RouterView />
  </section>
</template>

<style scoped>
.focus-layout {
  display: grid;
  grid-template-rows: 52px minmax(0, 1fr);
  height: 100dvh;
  overflow: hidden;
  color: var(--vdw-focus-ink);
  background: var(--vdw-focus-canvas);
}

.focus-header {
  display: flex;
  align-items: center;
  padding: 0 14px;
  background: var(--vdw-focus-panel);
  border-bottom: 1px solid var(--vdw-focus-rule);
}

.focus-header-tools {
  flex: 1;
  min-width: 0;
  height: 100%;
}

.focus-header strong {
  color: var(--vdw-focus-primary);
  font: 700 14px var(--vdw-mono);
  letter-spacing: 0.12em;
}
</style>

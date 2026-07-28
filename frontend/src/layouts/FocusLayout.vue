<template>
  <section class="focus-layout">
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
  color: #e8eef2;
  background: #111820;
}

.focus-header {
  display: flex;
  align-items: center;
  padding: 0 14px;
  background: var(--vdw-ink);
  border-bottom: 1px solid #33414c;
}

.focus-header-tools {
  flex: 1;
  min-width: 0;
  height: 100%;
}

.focus-header strong {
  color: var(--vdw-mint);
  font: 700 13px var(--vdw-mono);
  letter-spacing: 0.12em;
}
</style>

<template>
  <!-- Inside a kanban card modal (CardModal provides it) the page header renders in place. -->
  <div v-if="inline" class="border-b">
    <slot>
      <header class="flex h-10.5 items-center justify-between gap-2 py-[7px] pl-4 pr-2">
        <div class="flex min-w-0 items-center gap-2 truncate">
          <slot name="left-header" />
        </div>
        <div class="flex items-center gap-2">
          <slot name="right-header" class="flex items-center gap-2" />
        </div>
      </header>
    </slot>
  </div>
  <Teleport v-else-if="showHeader" to="#app-header">
    <slot>
      <header
        class="flex h-10.5 items-center justify-between py-[7px] sm:pl-5 pl-2"
      >
        <div class="flex items-center gap-2">
          <slot name="left-header" />
        </div>
        <div class="flex items-center gap-2">
          <slot name="right-header" class="flex items-center gap-2" />
        </div>
      </header>
    </slot>
  </Teleport>
</template>
<script setup>
import { ref, nextTick, inject } from 'vue'

const inline = inject('inlineLayoutHeader', false)
const showHeader = ref(false)

nextTick(() => {
  showHeader.value = true
})
</script>

<template>
  <div v-if="names.length" class="flex flex-wrap gap-1">
    <span
      v-for="name in names"
      :key="name"
      class="inline-flex max-w-full items-center truncate rounded font-medium"
      :class="size == 'sm' ? 'h-4 px-1.5 text-xs' : 'h-7 px-2.5 text-sm'"
      :style="styleFor(colorOf(name))"
      :title="name"
    >
      <span class="truncate">{{ name }}</span>
    </span>
  </div>
</template>

<script setup>
import { labelsStore } from '@/stores/labels'

defineProps({
  names: { type: Array, default: () => [] },
  size: { type: String, default: 'md' },
})

const { styleFor, colorOf } = labelsStore()
</script>

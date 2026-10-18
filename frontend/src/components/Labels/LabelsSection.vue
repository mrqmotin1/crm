<template>
  <div class="flex flex-col gap-1.5 border-b px-5 py-3">
    <div class="text-xs font-medium text-ink-gray-5">{{ __('Labels') }}</div>
    <div class="flex flex-wrap items-center gap-1">
      <LabelChips :names="names" />
      <Popover placement="bottom-start">
        <template #target="{ togglePopover }">
          <Button
            icon="plus"
            :tooltip="__('Labels')"
            :aria-label="__('Labels')"
            @click="togglePopover"
          />
        </template>
        <template #body="{ close }">
          <LabelsPicker
            v-model="names"
            :doctype="doctype"
            :docname="docname"
            @close="close"
          />
        </template>
      </Popover>
    </div>
  </div>
</template>

<script setup>
import { Popover } from 'frappe-ui'
import { computed } from 'vue'
import LabelChips from '@/components/Labels/LabelChips.vue'
import LabelsPicker from '@/components/Labels/LabelsPicker.vue'
import { parseLabels } from '@/stores/labels'

defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})
// The document's `labels` field: a JSON list of label names (saved by the picker itself).
const value = defineModel({ type: String, default: null })

const names = computed({
  get: () => parseLabels(value.value),
  set: (list) => {
    value.value = list.length ? JSON.stringify(list) : null
  },
})
</script>

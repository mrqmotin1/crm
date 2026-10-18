<template>
  <div>
    <div class="mb-2 text-base text-ink-gray-8">{{ __('Board background') }}</div>
    <div class="mb-2 grid grid-cols-6 gap-1.5">
      <button
        v-for="(css, key) in BOARD_GRADIENTS"
        :key="key"
        class="h-9 rounded"
        :class="ring('g:' + key)"
        :style="{ background: css }"
        :title="key"
        @click="set('g:' + key)"
      />
    </div>
    <div class="mb-2 grid grid-cols-10 gap-1.5">
      <button
        v-for="c in BOARD_COLORS"
        :key="c"
        class="h-7 rounded"
        :class="ring(c)"
        :style="{ background: c }"
        :title="c"
        @click="set(c)"
      />
    </div>
    <div class="flex items-center gap-2">
      <TextInput
        v-model="imageUrl"
        class="flex-1"
        :placeholder="__('Image URL (https://…)')"
        @keydown.enter="imageUrl && set(imageUrl)"
      />
      <FileUploader
        :fileTypes="['image/*']"
        :uploadArgs="{ private: false }"
        @success="(file) => set(file.file_url)"
      >
        <template #default="{ openFileSelector, uploading }">
          <Button :label="__('Upload')" :loading="uploading" @click="openFileSelector" />
        </template>
      </FileUploader>
      <Button v-if="modelValue" :label="__('None')" @click="set(null)" />
    </div>
  </div>
</template>

<script setup>
// Trello-style board background for the current kanban view (crm.api.views.set_kanban_background).
import { call, toast, FileUploader, TextInput } from 'frappe-ui'
import { ref } from 'vue'
import { BOARD_COLORS, BOARD_GRADIENTS } from '@/utils/boardBackground'
import { viewsStore } from '@/stores/views'

const props = defineProps({
  doctype: { type: String, required: true },
  view: { type: String, default: null },
  modelValue: { type: String, default: null },
})
const imageUrl = ref('')
const { reload } = viewsStore()

const ring = (v) => (props.modelValue == v ? 'ring-2 ring-offset-1 ring-outline-gray-5' : '')

async function set(value) {
  try {
    await call('crm.api.views.set_kanban_background', {
      doctype: props.doctype,
      view: props.view,
      background: value,
    })
    reload()
  } catch (err) {
    toast.error(err?.messages?.[0]?.replace(/<[^>]*>/g, '') || __('Could not set the background'))
  }
}
</script>

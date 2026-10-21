<template>
  <div class="w-72 rounded-lg bg-surface-elevation-2 p-3 shadow-2xl ring-1 ring-black ring-opacity-5">
    <div class="relative mb-3 flex items-center justify-center">
      <Button
        v-if="editing"
        class="absolute left-0"
        variant="ghost"
        size="sm"
        icon="chevron-left"
        @click="editing = null"
      />
      <div class="text-base font-semibold text-ink-gray-8">
        {{ editing ? (editing.name ? __('Edit label') : __('Create label')) : __('Labels') }}
      </div>
      <Button class="absolute right-0" variant="ghost" size="sm" icon="x" @click="emit('close')" />
    </div>

    <template v-if="!editing">
      <TextInput v-model="search" :placeholder="__('Search labels...')" class="mb-3" autofocus />
      <div class="mb-1 text-xs font-medium text-ink-gray-5">{{ __('Labels') }}</div>
      <div class="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
        <div v-for="l in filtered" :key="l.name" class="flex items-center gap-2">
          <input
            type="checkbox"
            class="size-4 rounded"
            :checked="selected.includes(l.name)"
            @change="toggle(l.name)"
          />
          <button
            class="h-8 flex-1 truncate rounded px-3 text-left text-sm font-medium"
            :style="styleFor(l.color)"
            @click="toggle(l.name)"
          >
            {{ l.label }}
          </button>
          <Button variant="ghost" size="sm" icon="edit-2" @click="startEdit(l)" />
        </div>
        <div v-if="!filtered.length" class="py-2 text-center text-sm text-ink-gray-5">
          {{ __('No labels') }}
        </div>
      </div>
      <Button class="mt-3 w-full" :label="__('Create a new label')" @click="startEdit(null)" />
    </template>

    <template v-else>
      <div
        class="mb-3 flex h-9 items-center justify-center truncate rounded px-3 text-sm font-medium"
        :style="styleFor(editing.color)"
      >
        {{ editing.label || __('Label preview') }}
      </div>
      <div class="mb-1 text-xs font-medium text-ink-gray-5">{{ __('Title') }}</div>
      <TextInput v-model="editing.label" class="mb-3" autofocus @keydown.enter="save" />
      <div class="mb-1 text-xs font-medium text-ink-gray-5">{{ __('Select a color') }}</div>
      <div class="mb-3 grid grid-cols-6 gap-1.5">
        <button
          v-for="(c, key) in LABEL_COLORS"
          :key="key"
          class="h-7 rounded"
          :class="editing.color == key ? 'ring-2 ring-offset-1 ring-outline-gray-5' : ''"
          :style="{ backgroundColor: c.bg }"
          :title="key"
          @click="editing.color = key"
        />
      </div>
      <div class="flex gap-2">
        <Button variant="solid" class="flex-1" :label="__('Save')" :loading="busy" @click="save" />
        <Button
          v-if="editing.name"
          theme="red"
          :label="__('Delete')"
          :loading="busy"
          @click="remove"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
// Trello-style label picker: search, tick to apply, edit (rename/recolour/delete), create.
import { call, toast, TextInput } from 'frappe-ui'
import { computed, ref } from 'vue'
import { labelsStore, LABEL_COLORS } from '@/stores/labels'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})
const selected = defineModel({ type: Array, default: () => [] })
const emit = defineEmits(['close'])

const { labels, styleFor } = labelsStore()
const search = ref('')
const editing = ref(null)
const busy = ref(false)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return (labels.data || []).filter((l) => !q || l.label.toLowerCase().includes(q))
})

function errorOf(err) {
  return err?.messages?.[0]?.replace(/<[^>]*>/g, '') || __('Something went wrong')
}

async function persist(names) {
  try {
    selected.value = await call('crm.api.labels.set_labels', {
      doctype: props.doctype,
      name: props.docname,
      labels: names,
    })
  } catch (err) {
    toast.error(errorOf(err))
  }
}

function toggle(name) {
  const names = selected.value.includes(name)
    ? selected.value.filter((n) => n !== name)
    : [...selected.value, name]
  selected.value = names
  persist(names)
}

function startEdit(label) {
  editing.value = label
    ? { name: label.name, label: label.label, color: label.color }
    : { name: null, label: search.value.trim(), color: 'green' }
}

async function save() {
  if (!editing.value.label?.trim()) return
  busy.value = true
  try {
    const saved = await call('crm.api.labels.save_label', {
      name: editing.value.name,
      label: editing.value.label.trim(),
      color: editing.value.color,
    })
    const wasNew = !editing.value.name
    const renamedFrom = editing.value.name !== saved.name ? editing.value.name : null
    await labels.reload()
    if (renamedFrom) {
      selected.value = selected.value.map((n) => (n === renamedFrom ? saved.name : n))
    }
    if (wasNew) toggle(saved.name)
    editing.value = null
    search.value = ''
  } catch (err) {
    toast.error(errorOf(err))
  } finally {
    busy.value = false
  }
}

async function remove() {
  busy.value = true
  try {
    await call('crm.api.labels.delete_label', { name: editing.value.name })
    selected.value = selected.value.filter((n) => n !== editing.value.name)
    await labels.reload()
    editing.value = null
  } catch (err) {
    toast.error(errorOf(err))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="show" size="sm" bare>
    <LabelsPicker
      v-if="loaded"
      v-model="names"
      class="!w-full !shadow-none !ring-0"
      :doctype="doctype"
      :docname="name"
      @close="show = false"
    />
  </Dialog>
</template>

<script setup>
// "Edit labels" from a kanban card's quick menu, without opening the card.
import { Dialog, call } from 'frappe-ui'
import { ref, watch } from 'vue'
import LabelsPicker from '@/components/Labels/LabelsPicker.vue'
import { parseLabels } from '@/stores/labels'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
})
const emit = defineEmits(['close'])
const show = ref(true)
const names = ref([])
const loaded = ref(false)

call('frappe.client.get_value', { doctype: props.doctype, filters: props.name, fieldname: 'labels' }).then((r) => {
  names.value = parseLabels(r?.labels)
  loaded.value = true
})

watch(show, (open) => {
  if (!open) emit('close')
})
</script>

<template>
  <Dialog v-model:open="show" :title="options.title || __('Lost Reason')" @close="cancel">
    <template #default>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        {{
          options.message ||
          __('Please provide a reason for marking this {0} as lost', [
            doctype.toLowerCase().replace('crm ', ''),
          ])
        }}
      </div>
      <div class="flex flex-col gap-3">
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ options.field_label || __('Lost Reason') }}
            <span class="text-ink-red-5">*</span>
          </div>
          <FormControl
            v-if="options.reasons"
            v-model="lostReason"
            type="select"
            :options="['', ...options.reasons]"
          />
          <Link
            v-else
            ref="linkRef"
            class="form-control flex-1 truncate"
            :value="lostReason"
            doctype="CRM Lost Reason"
            :onCreate="options.allow_create === false ? null : onCreate"
            @change="(v) => (lostReason = v)"
          />
        </div>
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ __('Lost Notes') }}
            <span v-if="lostReason == 'Other'" class="text-ink-red-5">*</span>
          </div>
          <FormControl
            v-model="lostNotes"
            class="form-control flex-1 truncate"
            type="textarea"
          />
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-between items-center gap-2">
        <div class="flex items-center gap-2">
          <Button
            v-if="options.assist"
            :label="options.assist.label"
            :loading="assisting"
            @click="assist"
          />
          <ErrorMessage :message="error" />
        </div>
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="cancel" />
          <Button variant="solid" :label="__('Save')" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import Link from '@/components/Controls/Link.vue'
import { createDocument } from '@/composables/document'
import { Dialog, call } from 'frappe-ui'
import { ref, reactive, onMounted } from 'vue'

const props = defineProps({
  doctype: { type: String, default: 'CRM Lead' },
  document: { type: Object, default: null },
  // kanban moves have no document: the target status and record name
  status: { type: String, default: '' },
  name: { type: String, default: '' },
})

const emit = defineEmits(['save', 'cancel'])

const show = defineModel({ type: Boolean })

const linkRef = ref(null)
const doc = props.document?.doc
const lostReason = ref(doc?.lost_reason || '')
const lostNotes = ref(doc?.lost_notes || '')
const error = ref('')
const assisting = ref(false)
const options = reactive({})
const targetStatus = () => props.status || doc?.status || ''
const targetName = () => props.name || doc?.name || ''

onMounted(async () => {
  try {
    Object.assign(
      options,
      await call('crm.api.lost_reasons.get_options', {
        doctype: props.doctype,
        status: targetStatus(),
        name: targetName(),
      }),
    )
    if (options.reasons && lostReason.value && !options.reasons.includes(lostReason.value)) {
      lostReason.value = ''
    }
  } catch (e) {
    // keep the plain dialog
  }
})

async function assist() {
  assisting.value = true
  error.value = ''
  try {
    let r = await call(options.assist.method, {
      doctype: props.doctype,
      name: targetName(),
      status: targetStatus(),
      reasons: JSON.stringify(options.reasons || []),
      notes: lostNotes.value,
    })
    if (r?.lost_reason) lostReason.value = r.lost_reason
    if (r?.lost_notes) lostNotes.value = r.lost_notes
  } catch (e) {
    error.value = e?.messages?.[0] || __('Could not suggest a reason')
  } finally {
    assisting.value = false
  }
}

function cancel() {
  show.value = false
  error.value = ''
  lostReason.value = ''
  lostNotes.value = ''
  if (doc) {
    doc.status = props.document.originalDoc.status
  }
  emit('cancel')
}

function save() {
  if (!lostReason.value) {
    error.value = __('Lost Reason is required')
    return
  }
  if (lostReason.value === 'Other' && !lostNotes.value) {
    error.value = __('Lost Notes are required when Lost Reason is "Other"')
    return
  }

  error.value = ''
  show.value = false

  if (doc) {
    doc.lost_reason = lostReason.value
    doc.lost_notes = lostNotes.value
    props.document.save.submit()
  }
  emit('save', { lost_reason: lostReason.value, lost_notes: lostNotes.value })
  lostReason.value = ''
  lostNotes.value = ''
}

function onCreate(value, close) {
  let doc = { lost_reason: value }
  createDocument('CRM Lost Reason', doc, close, (doc) => {
    lostReason.value = doc.name
    linkRef.value?.reload('', true)
  })
}
</script>

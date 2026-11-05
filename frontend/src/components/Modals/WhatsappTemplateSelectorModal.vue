<template>
  <Dialog v-model:open="show" :title="__('WhatsApp Templates')" :size="'4xl'">
    <template #default>
      <div v-if="form" class="flex flex-col gap-3">
        <div class="flex items-center gap-2">
          <Button
            variant="ghost"
            icon="arrow-left"
            @click="form.step === 'confirm' ? (form.step = 'edit') : (form = null)"
          />
          <div class="text-base-semibold truncate">{{ form.template }}</div>
          <div v-if="form.step === 'edit'" class="ml-auto flex gap-1">
            <Button
              v-for="code in form.languages"
              :key="code"
              :label="code === 'bn' ? 'বাংলা' : 'English'"
              :variant="form.language === code ? 'solid' : 'subtle'"
              @click="openForm(form.template, code)"
            />
          </div>
        </div>
        <div
          v-if="form.blocked"
          class="rounded border border-outline-red-2 bg-surface-red-1 p-2 text-sm text-ink-red-4"
        >
          {{ form.blocked }}
        </div>
        <div v-if="form.step === 'confirm'" class="text-base text-ink-gray-8">
          {{ __('Send this message to {0}?', [form.to || '']) }}
        </div>
        <!-- the message as the customer will see it; values are escaped, and the whole is passed through
             sanitizeHTML() (DOMPurify), so v-html is safe here -->
        <!-- eslint-disable vue/no-v-html -->
        <div class="rounded-lg bg-surface-gray-2 p-3">
          <div
            class="max-w-[520px] whitespace-pre-wrap rounded-lg bg-surface-base p-3 text-sm text-ink-gray-8 shadow-sm"
            v-html="sanitizeHTML(preview)"
          />
          <div
            v-if="form.button"
            class="mt-1 max-w-[520px] rounded-lg bg-surface-base p-2 text-center text-sm text-ink-blue-3 shadow-sm"
          >
            <span class="lucide-external-link mr-1 inline-block h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
            {{ form.button.label }}
            <div class="truncate text-xs text-ink-gray-5" :title="buttonUrl">{{ buttonUrl }}</div>
          </div>
        </div>
        <!-- eslint-enable vue/no-v-html -->
        <template v-if="form.step === 'edit'">
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <FormControl
              v-for="field in form.fields"
              :key="field.key"
              v-model="field.value"
              :label="field.label"
              maxlength="60"
            />
          </div>
          <div class="flex items-center justify-between gap-2">
            <div class="text-sm text-ink-gray-5">
              {{ __('To') }}: {{ form.to || '—' }}
              <span v-if="form.category"> · {{ form.category }}</span>
            </div>
            <Button
              :label="__('Review')"
              variant="solid"
              :disabled="!canSend"
              @click="form.step = 'confirm'"
            />
          </div>
        </template>
        <div v-else class="flex justify-end gap-2">
          <Button :label="__('Back')" @click="form.step = 'edit'" />
          <Button
            :label="__('Confirm & send')"
            variant="solid"
            theme="green"
            :disabled="!canSend"
            @click="sendForm"
          />
        </div>
      </div>
      <template v-else>
        <div class="w-full flex items-center gap-2">
          <TextInput
            ref="searchInput"
            v-model="search"
            class="w-full"
            type="text"
            :placeholder="__('Welcome Message')"
          >
            <template #prefix>
              <span
                class="lucide-search h-4 w-4 text-ink-gray-4"
                aria-hidden="true"
              />
            </template>
          </TextInput>
          <Button
            :label="__('Create New Template')"
            variant="solid"
            @click="newWhatsappTemplate"
          >
            <template #prefix>
              <span class="lucide-plus h-4 w-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <div v-if="groups.length" class="mt-2 flex flex-wrap gap-1.5">
          <Button
            v-for="g in [...groups, { key: 'all', label: __('All') }]"
            :key="g.key"
            size="sm"
            :variant="group === g.key ? 'solid' : 'subtle'"
            @click="group = g.key"
          >
            {{ g.label }}
            <span v-if="g.key === defaultGroup" class="ml-1 opacity-70">· {{ __('this lead') }}</span>
          </Button>
        </div>
        <div
          v-if="filteredTemplates.length"
          class="mt-2 grid max-h-[520px] grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-3"
        >
          <div
            v-for="template in filteredTemplates"
            :key="template.name"
            class="flex h-56 cursor-pointer flex-col gap-2 rounded-lg border p-3 hover:bg-surface-gray-2"
            @click="pick(template)"
          >
            <div
              class="border-b pb-2 text-base-semibold truncate"
              :title="template.key"
            >
              {{ template.key }}
            </div>
            <!-- content is passed through sanitizeHTML() (DOMPurify) before rendering, so v-html is safe here -->
            <!-- eslint-disable vue/no-v-html -->
            <div
              v-if="template.template"
              class="prose-f prose-sm max-w-none !text-sm text-ink-gray-5 flex-1 overflow-hidden"
              v-html="sanitizeHTML(template.template)"
            />
            <!-- eslint-enable vue/no-v-html -->
          </div>
        </div>
        <div v-else class="mt-2">
          <div class="flex h-56 flex-col items-center justify-center">
            <div class="text-lg text-ink-gray-4">
              {{ __('No Templates Found') }}
            </div>
            <Button
              :label="__('Create New')"
              class="mt-4"
              @click="newWhatsappTemplate"
            />
          </div>
        </div>
      </template>
    </template>
  </Dialog>
</template>

<script setup>
import { createListResource, call, toast, FormControl } from 'frappe-ui'
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { sanitizeHTML } from '@/utils'

const props = defineProps({
  doctype: { type: String, default: '' },
  // the record the message is for: lets an app ask for the language and variables (hook crm_whatsapp_template_form)
  // and group the templates by stage (hook crm_whatsapp_template_groups)
  referenceDoctype: { type: String, default: '' },
  referenceName: { type: String, default: '' },
})

const show = defineModel({ type: Boolean })
const searchInput = ref('')

const emit = defineEmits(['send'])

const search = ref('')

const templates = createListResource({
  type: 'list',
  doctype: 'WhatsApp Templates',
  cache: ['whatsappTemplates'],
  fields: ['name', 'template', 'footer', 'actual_name', 'language_code'],
  filters: { status: 'APPROVED', for_doctype: ['in', [props.doctype, '']] },
  orderBy: 'modified desc',
  pageLength: 99999,
})

onMounted(() => {
  if (templates.data == null) {
    templates.fetch()
  }
})

// one card per Meta template (its Bangla and English records together), Bangla text first
const grouped = computed(() => {
  const byKey = {}
  for (const t of templates.data ?? []) {
    const key = t.actual_name || t.name
    byKey[key] ??= { key, records: {} }
    byKey[key].records[t.language_code || 'en'] = t
  }
  return Object.values(byKey).map((g) => {
    const first = g.records.bn || g.records.en || Object.values(g.records)[0]
    return { ...g, name: first.name, template: first.template, languages: Object.keys(g.records) }
  })
})

// stage chips from the app; the record's own stage is chosen when the picker opens
const groups = ref([])
const hidden = ref([])
const defaultGroup = ref(null)
const group = ref('all')

async function loadGroups() {
  groups.value = []
  hidden.value = []
  defaultGroup.value = null
  group.value = 'all'
  if (!props.referenceName) return
  try {
    const out = await call('crm.api.whatsapp.whatsapp_template_groups', {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
    })
    groups.value = out?.groups || []
    hidden.value = out?.hidden || []
    defaultGroup.value = out?.default || null
    group.value = defaultGroup.value || 'all'
  } catch {
    // no chips: every template stays listed
  }
}

const filteredTemplates = computed(() => {
  const chosen = groups.value.find((g) => g.key === group.value)
  return grouped.value.filter(
    (t) =>
      !hidden.value.includes(t.key) &&
      (!chosen || chosen.templates.includes(t.key)) &&
      t.key.toLowerCase().includes(search.value.toLowerCase()),
  )
})

const form = ref(null)

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}

// the body's {{1}}, {{2}}… are the form's fields in order, except the button's own variable
const bodyFields = computed(() =>
  (form.value?.fields || []).filter((f) => f.key !== form.value?.button?.var),
)

const preview = computed(() => {
  if (!form.value) return ''
  const group = grouped.value.find((g) => g.key === form.value.template)
  const body = escapeHtml(group?.records[form.value.language]?.template || group?.template || '')
  return bodyFields.value.reduce((text, f, i) => {
    const value = String(f.value || '').trim()
    return text.split(`{{${i + 1}}}`).join(value ? `<b>${escapeHtml(value)}</b>` : `<span class="text-ink-red-4">{{${i + 1}}}</span>`)
  }, body)
})

const buttonUrl = computed(() => {
  const b = form.value?.button
  if (!b?.url) return ''
  const value = b.var ? form.value.fields.find((f) => f.key === b.var)?.value : ''
  return b.url.split('{{1}}').join(String(value || '').trim() || '{{1}}')
})

const canSend = computed(
  () =>
    form.value &&
    form.value.approved &&
    !form.value.blocked &&
    form.value.fields.every((f) => String(f.value || '').trim()),
)

async function openForm(key, language) {
  const out = await call('crm.api.whatsapp.whatsapp_template_form', {
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
    template: key,
    language,
  })
  if (!out) return false
  const group = grouped.value.find((g) => g.key === key)
  form.value = { ...out, step: 'edit', template: key, languages: group?.languages || [out.language] }
  return true
}

async function pick(template) {
  if (props.referenceName) {
    try {
      if (await openForm(template.key)) return
    } catch (e) {
      toast.error(e.messages?.[0] || __('Could not load the template'))
      return
    }
  }
  emit('send', template.name)
}

function sendForm() {
  if (!canSend.value) return
  const values = Object.fromEntries(form.value.fields.map((f) => [f.key, String(f.value).trim()]))
  emit('send', { template: form.value.template, language: form.value.language, values })
  form.value = null
}

function newWhatsappTemplate() {
  show.value = false
  window.open('/app/whatsapp-templates/new')
}

watch(show, (value) => {
  if (!value) {
    form.value = null
    return
  }
  loadGroups()
  nextTick(() => searchInput.value?.el?.focus())
})
</script>

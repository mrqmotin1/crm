<template>
  <Dialog v-model:open="show" :title="__('WhatsApp Templates')" :size="'4xl'">
    <template #default>
      <div v-if="form" class="flex flex-col gap-3">
        <div class="flex items-center gap-2">
          <Button variant="ghost" icon="arrow-left" @click="form = null" />
          <div class="text-base-semibold truncate">{{ form.template }}</div>
          <div class="ml-auto flex gap-1">
            <Button
              v-for="code in form.languages"
              :key="code"
              :label="code === 'bn' ? 'বাংলা' : 'English'"
              :variant="form.language === code ? 'solid' : 'subtle'"
              @click="openForm(form.template, code)"
            />
          </div>
        </div>
        <div v-if="form.opted_out" class="text-sm text-ink-red-4">
          {{ __('This lead asked for no more messages: Marketing templates are refused.') }}
        </div>
        <div v-if="!form.approved" class="text-sm text-ink-amber-4">
          {{ __('Not approved by Meta in this language yet.') }}
        </div>
        <!-- content is passed through sanitizeHTML() (DOMPurify) before rendering, so v-html is safe here -->
        <!-- eslint-disable vue/no-v-html -->
        <div
          class="prose-f prose-sm max-w-none rounded border p-3 !text-sm text-ink-gray-6"
          v-html="sanitizeHTML(preview)"
        />
        <!-- eslint-enable vue/no-v-html -->
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <FormControl
            v-for="field in form.fields"
            :key="field.key"
            v-model="field.value"
            :label="field.label"
            maxlength="60"
          />
        </div>
        <div class="flex justify-end">
          <Button
            :label="__('Send')"
            variant="solid"
            :loading="sending"
            :disabled="!form.approved || form.fields.some((f) => !String(f.value || '').trim())"
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
      <div
        v-if="filteredTemplates.length"
        class="mt-2 grid max-h-[560px] grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-3"
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
  // the record the message is for: lets an app (hook crm_whatsapp_template_form) ask for the language and variables
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

const filteredTemplates = computed(() =>
  grouped.value.filter((t) => t.key.toLowerCase().includes(search.value.toLowerCase())),
)

const form = ref(null)
const sending = ref(false)

const preview = computed(() => {
  if (!form.value) return ''
  const group = grouped.value.find((g) => g.key === form.value.template)
  const body = group?.records[form.value.language]?.template || group?.template || ''
  return form.value.fields.reduce(
    (text, f, i) => text.split(`{{${i + 1}}}`).join(f.value ? `<b>${f.value}</b>` : `{{${i + 1}}}`),
    body,
  )
})

async function openForm(key, language) {
  const out = await call('crm.api.whatsapp.whatsapp_template_form', {
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
    template: key,
    language,
  })
  if (!out) return false
  const group = grouped.value.find((g) => g.key === key)
  form.value = { ...out, template: key, languages: group?.languages || [out.language] }
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
  const values = Object.fromEntries(form.value.fields.map((f) => [f.key, String(f.value).trim()]))
  emit('send', { template: form.value.template, language: form.value.language, values })
  form.value = null
}

function newWhatsappTemplate() {
  show.value = false
  window.open('/app/whatsapp-templates/new')
}

watch(show, (value) => {
  if (!value) form.value = null
  value && nextTick(() => searchInput.value?.el?.focus())
})
</script>

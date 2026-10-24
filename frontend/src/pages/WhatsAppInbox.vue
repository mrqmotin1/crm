<template>
  <div class="flex h-full flex-col overflow-hidden">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="[{ label: __('WhatsApp'), route: { name: 'WhatsApp' } }]" />
      </template>
      <template #right-header>
        <Button
          :label="__('Refresh')"
          icon-left="refresh-cw"
          @click="reloadAll"
        />
      </template>
    </LayoutHeader>
    <div class="flex flex-1 overflow-hidden">
      <!-- conversations -->
      <div
        v-show="!isMobileView || !selected"
        class="flex w-full shrink-0 flex-col border-r sm:w-80"
      >
        <div class="flex flex-col gap-2 border-b p-3">
          <TabButtons v-model="scope" :buttons="scopeButtons" class="w-full" />
          <div class="flex items-center gap-2">
            <TextInput
              v-model="search"
              class="flex-1"
              type="text"
              :placeholder="__('Search name, number, message')"
              :debounce="300"
            />
            <Button
              :variant="unreadOnly ? 'solid' : 'subtle'"
              :label="__('Unread')"
              @click="unreadOnly = !unreadOnly"
            />
          </div>
          <div class="flex items-center gap-2 text-sm text-ink-gray-5">
            <span>{{ __('Show') }}</span>
            <Button
              size="sm"
              :variant="status == 'Open' ? 'solid' : 'ghost'"
              :label="__('Open')"
              @click="status = 'Open'"
            />
            <Button
              size="sm"
              :variant="status == 'Done' ? 'solid' : 'ghost'"
              :label="__('Done')"
              @click="status = 'Done'"
            />
          </div>
        </div>
        <div class="flex-1 overflow-y-auto">
          <div
            v-for="c in conversations.data || []"
            :key="c.name"
            class="flex cursor-pointer flex-col gap-1 border-b px-3 py-2.5 hover:bg-surface-gray-1"
            :class="selected == c.name ? 'bg-surface-gray-2' : ''"
            @click="open(c.name)"
          >
            <div class="flex items-center justify-between gap-2">
              <div
                class="truncate text-base"
                :class="c.unread ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-8'"
              >
                {{ c.reference_title || c.profile_name || '+' + c.contact_number }}
              </div>
              <div class="shrink-0 text-xs text-ink-gray-5">
                {{ c.last_message_at ? shortTime(c.last_message_at) : '' }}
              </div>
            </div>
            <div class="flex items-center justify-between gap-2">
              <div class="truncate text-sm text-ink-gray-5">
                <span v-if="c.last_direction == 'Outgoing'">{{ __('You') }}: </span>
                {{ c.last_message }}
              </div>
              <span
                v-if="c.unread"
                class="flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-green-600 px-1 text-2xs font-medium text-white"
              >
                {{ c.unread }}
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-1">
              <Badge
                v-if="c.reference_status"
                size="sm"
                variant="subtle"
                :label="c.reference_status"
              />
              <Badge
                v-else
                size="sm"
                theme="orange"
                variant="subtle"
                :label="__('Not linked')"
              />
              <Badge
                v-if="!c.owner_user"
                size="sm"
                theme="blue"
                variant="subtle"
                :label="__('Unclaimed')"
              />
              <span class="truncate text-xs text-ink-gray-4">
                {{ __('on {0}', [c.account_label]) }}
              </span>
            </div>
          </div>
          <div
            v-if="conversations.data && !conversations.data.length"
            class="p-6 text-center text-base text-ink-gray-5"
          >
            {{ __('No conversations') }}
          </div>
        </div>
      </div>

      <!-- thread -->
      <div v-if="selected && conversation.data" class="flex flex-1 flex-col overflow-hidden">
        <div class="flex items-center justify-between gap-2 border-b px-3 py-2 sm:px-5">
          <div class="flex min-w-0 items-center gap-2">
            <Button
              v-if="isMobileView"
              variant="ghost"
              icon="arrow-left"
              @click="selected = null"
            />
            <div class="min-w-0">
              <div class="truncate text-lg font-medium text-ink-gray-9">
                {{
                  conversation.data.reference?.title ||
                  conversation.data.profile_name ||
                  '+' + conversation.data.contact_number
                }}
              </div>
              <div class="truncate text-sm text-ink-gray-5">
                +{{ conversation.data.contact_number }}
                <span v-if="conversation.data.profile_name">
                  · {{ conversation.data.profile_name }}</span
                >
                · {{ __('to {0}', [conversation.data.account_label]) }}
              </div>
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <template v-if="conversation.data.reference">
              <Badge variant="subtle" :label="conversation.data.reference.status" />
              <Button
                :label="isMobileView ? '' : __('Open')"
                icon-left="external-link"
                @click="openRecord(conversation.data.reference)"
              />
            </template>
            <Button
              v-else
              variant="solid"
              :label="__('Create lead')"
              :loading="creatingLead"
              @click="createLead"
            />
            <Button
              v-if="conversation.data.status == 'Open'"
              :label="__('Done')"
              icon-left="check"
              @click="setStatus('Done')"
            />
            <Button v-else :label="__('Reopen')" @click="setStatus('Open')" />
          </div>
        </div>
        <div ref="threadEl" class="flex-1 overflow-y-auto px-3 py-4 sm:px-10">
          <WhatsAppArea
            v-if="thread.data?.length"
            v-model="thread"
            v-model:reply="reply"
            :messages="thread.data"
          />
        </div>
        <div class="border-t">
          <div
            v-if="!conversation.data.can_send"
            class="px-3 py-3 text-sm text-ink-gray-5 sm:px-10"
          >
            {{ __("Receive-only: sending isn't switched on for this WhatsApp number yet.") }}
          </div>
          <div
            v-else-if="!conversation.data.window_open"
            class="flex items-center justify-between gap-2 px-3 py-3 sm:px-10"
          >
            <span class="text-sm text-ink-gray-5">
              {{ __('More than 24 hours since the customer last wrote: WhatsApp allows an approved template only.') }}
            </span>
            <Button
              variant="solid"
              :label="__('Send template')"
              @click="showTemplates = true"
            />
          </div>
          <template v-else>
            <div
              v-if="reply?.message"
              class="flex items-center gap-2 px-3 pt-2 sm:px-10"
            >
              <div
                class="max-h-12 flex-1 overflow-hidden rounded border-l-4 border-green-500 bg-surface-gray-2 p-2 text-sm text-ink-gray-5"
                v-html="reply.message"
              />
              <Button variant="ghost" icon="x" @click="reply = {}" />
            </div>
            <div class="flex items-end gap-2 px-3 py-2.5 sm:px-10">
              <FileUploader @success="(file) => sendFile(file)">
                <template #default="{ openFileSelector }">
                  <Dropdown :options="uploadOptions(openFileSelector)">
                    <Button variant="ghost" icon="plus" />
                  </Dropdown>
                </template>
              </FileUploader>
              <Textarea
                v-model="content"
                class="min-h-8 w-full"
                :rows="rows"
                :placeholder="__('Type your message here...')"
                @focus="rows = 4"
                @blur="rows = 1"
                @keydown.enter.exact.prevent="sendText"
              />
              <Button
                variant="solid"
                icon="send"
                :loading="sending"
                :disabled="!content.trim()"
                @click="sendText"
              />
            </div>
          </template>
        </div>
      </div>
      <div
        v-else-if="!isMobileView"
        class="flex flex-1 items-center justify-center text-base text-ink-gray-5"
      >
        {{ __('Pick a conversation') }}
      </div>
    </div>
    <WhatsappTemplateSelectorModal
      v-model="showTemplates"
      :doctype="conversation.data?.reference_doctype || ''"
      @send="(t) => sendTemplate(t)"
    />
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import WhatsAppArea from '@/components/Activities/WhatsAppArea.vue'
import WhatsappTemplateSelectorModal from '@/components/Modals/WhatsappTemplateSelectorModal.vue'
import { isMobileView } from '@/composables/settings'
import { refreshWhatsappUnread } from '@/composables/whatsapp'
import { globalStore } from '@/stores/global'
import { formatDate, timeAgo } from '@/utils'
import {
  Badge,
  Breadcrumbs,
  Button,
  Dropdown,
  FileUploader,
  TabButtons,
  Textarea,
  TextInput,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const { $socket } = globalStore()

const scopeButtons = [
  { label: __('All'), value: 'all' },
  { label: __('Mine'), value: 'mine' },
  { label: __('Unclaimed'), value: 'unassigned' },
]
const scope = ref('all')
const search = ref('')
const unreadOnly = ref(false)
const status = ref('Open')
const selected = ref(route.query.c || null)
const reply = ref({})
const content = ref('')
const rows = ref(1)
const sending = ref(false)
const creatingLead = ref(false)
const showTemplates = ref(false)
const threadEl = ref(null)

const conversations = createResource({
  url: 'crm.api.whatsapp_inbox.list_conversations',
  makeParams: () => ({
    scope: scope.value,
    unread: unreadOnly.value ? 1 : 0,
    search: search.value,
    status: status.value,
    limit: 100,
  }),
  auto: true,
})

const conversation = createResource({
  url: 'crm.api.whatsapp_inbox.get_conversation',
  makeParams: () => ({ conversation: selected.value }),
})

const thread = createResource({
  url: 'crm.api.whatsapp_inbox.get_thread',
  makeParams: () => ({ conversation: selected.value }),
  transform: (data) =>
    data.sort((a, b) => new Date(a.creation) - new Date(b.creation)),
  onSuccess: () => nextTick(scrollToEnd),
})

watch([scope, search, unreadOnly, status], () => conversations.reload())

function load() {
  if (!selected.value) return
  conversation.reload()
  thread.reload()
  call('crm.api.whatsapp_inbox.mark_read', { conversation: selected.value }).then(
    () => refreshWhatsappUnread(),
  )
}

watch(
  selected,
  (name) => {
    reply.value = {}
    router.replace({ query: name ? { c: name } : {} })
    load()
  },
  { immediate: true },
)

function open(name) {
  selected.value = name
}

function reloadAll() {
  conversations.reload()
  load()
}

function scrollToEnd() {
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight
}

function shortTime(dt) {
  const d = new Date(dt.replace(' ', 'T'))
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return formatDate(dt, 'hh:mm a')
  return timeAgo(dt)
}

function openRecord(ref) {
  const name = ref.doctype === 'CRM Deal' ? 'Deal' : 'Lead'
  const params = name === 'Deal' ? { dealId: ref.name } : { leadId: ref.name }
  router.push({ name, params, hash: '#whatsapp' })
}

async function send(method, args) {
  sending.value = true
  try {
    await call(`crm.api.whatsapp_inbox.${method}`, {
      conversation: selected.value,
      ...args,
    })
    thread.reload()
    conversations.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Failed to send WhatsApp message'))
  } finally {
    sending.value = false
  }
}

function sendText() {
  const text = content.value.trim()
  if (!text) return
  content.value = ''
  const reply_to = reply.value?.name || ''
  reply.value = {}
  send('send', { message: text, reply_to })
}

const fileType = ref('document')
function sendFile(file) {
  send('send', {
    message: '',
    attach: file.file_url,
    content_type: fileType.value,
  })
}

function uploadOptions(openFileSelector) {
  return [
    {
      label: __('Upload Document'),
      icon: 'file',
      onClick: () => {
        fileType.value = 'document'
        openFileSelector()
      },
    },
    {
      label: __('Upload Image'),
      icon: 'image',
      onClick: () => {
        fileType.value = 'image'
        openFileSelector('image/*')
      },
    },
  ]
}

function sendTemplate(template) {
  showTemplates.value = false
  send('send_template', { template })
}

async function setStatus(value) {
  await call('crm.api.whatsapp_inbox.set_status', {
    conversation: selected.value,
    status: value,
  })
  conversation.reload()
  conversations.reload()
  refreshWhatsappUnread()
}

async function createLead() {
  creatingLead.value = true
  try {
    const lead = await call('crm.api.whatsapp_inbox.create_lead', {
      conversation: selected.value,
    })
    toast.success(__('Lead {0} created', [lead]))
    conversation.reload()
    conversations.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not create the lead'))
  } finally {
    creatingLead.value = false
  }
}

function onInbox(data) {
  conversations.reload()
  refreshWhatsappUnread()
  if (data?.conversation && data.conversation === selected.value) {
    thread.reload()
    conversation.reload()
    call('crm.api.whatsapp_inbox.mark_read', { conversation: selected.value })
  }
}

onMounted(() => $socket.on('whatsapp_inbox', onInbox))
onBeforeUnmount(() => $socket.off('whatsapp_inbox', onInbox))
</script>

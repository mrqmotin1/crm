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
            class="flex cursor-pointer items-start gap-3 border-b px-3 py-2.5 hover:bg-surface-gray-1"
            :class="selected == c.name ? 'bg-surface-gray-2' : ''"
            @click="open(c.name)"
          >
            <Avatar
              size="2xl"
              class="mt-0.5 shrink-0"
              :label="c.reference_title || c.profile_name || '#'"
            />
            <div class="flex min-w-0 flex-1 flex-col gap-1">
            <div class="flex items-center justify-between gap-2">
              <div
                class="truncate text-base"
                :class="c.unread ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-8'"
              >
                {{ c.reference_title || c.profile_name || '+' + c.contact_number }}
              </div>
              <div
                class="shrink-0 text-xs"
                :class="c.unread ? 'font-medium text-ink-green-5' : 'text-ink-gray-5'"
              >
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
                v-if="c.blocked"
                size="sm"
                theme="red"
                variant="subtle"
                :label="__('Blocked')"
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
      <div v-if="selected && conversation.data" class="wa-pane flex flex-1 flex-col overflow-hidden">
        <div class="wa-bar flex items-center justify-between gap-2 border-b px-3 py-2 sm:px-5">
          <div class="flex min-w-0 items-center gap-2">
            <Button
              v-if="isMobileView"
              variant="ghost"
              icon="arrow-left"
              @click="selected = null"
            />
            <Avatar
              size="2xl"
              class="shrink-0"
              :label="
                conversation.data.reference?.title || conversation.data.profile_name || '#'
              "
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
              v-if="!conversation.data.reference || conversation.data.reference.doctype == 'Contact'"
              variant="solid"
              :label="__('Create lead')"
              :loading="creatingLead"
              @click="createLead"
            />
            <template v-if="conversation.data.assistant">
              <Badge
                :theme="conversation.data.assistant.handler == 'Mona' ? 'green' : 'gray'"
                variant="subtle"
                :label="conversation.data.assistant.handler == 'Mona' ? __('✨ Mona answering') : conversation.data.assistant.handler == 'Paused' ? __('Mona paused') : __('Rep')"
                :title="conversation.data.assistant.reason || conversation.data.assistant.stage || ''"
              />
              <Button
                v-if="conversation.data.assistant.handler == 'Mona'"
                :label="isMobileView ? '' : __('Take over')"
                icon-left="user"
                @click="setHandler('Rep')"
              />
              <Button
                v-else
                :label="isMobileView ? '' : __('Hand back to Mona')"
                icon-left="corner-up-right"
                @click="setHandler('Mona')"
              />
            </template>
            <Button
              v-if="isMobileView && quickFields.length"
              :variant="showDetails ? 'subtle' : 'ghost'"
              icon="sliders"
              :title="__('Lead details')"
              @click="showDetails = !showDetails"
            />
            <Badge
              v-if="conversation.data.blocked"
              theme="red"
              variant="subtle"
              :label="__('Blocked')"
            />
            <Button
              v-else
              variant="ghost"
              icon="slash"
              :title="__('Block this number')"
              @click="blockNumber"
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
        <!-- details of the chat's lead that staff fill in while talking (hook crm_whatsapp_quick_fields) -->
        <div
          v-if="quickFields.length"
          v-show="!isMobileView || showDetails"
          class="wa-bar flex flex-wrap items-end gap-x-3 gap-y-2 border-b px-3 py-2 sm:px-5"
        >
          <div
            v-for="f in quickFields"
            :key="f.fieldname"
            class="min-w-0"
            :class="f.read_only ? 'max-w-56' : 'w-[calc(50%-0.375rem)] sm:w-40'"
          >
            <div class="mb-0.5 flex items-center gap-1 truncate text-xs text-ink-gray-5">
              <span class="truncate">{{ f.label }}</span>
              <button
                v-if="!f.read_only && f.question && conversation.data.can_send && conversation.data.window_open"
                type="button"
                class="shrink-0 rounded px-1 font-medium text-ink-blue-link hover:bg-surface-gray-3"
                :title="__('Put the question for the customer in the message box. Mona fills the field from the answer.')"
                @click="askQuick(f)"
              >
                {{ __('Ask') }}
              </button>
              <span v-if="savedField == f.fieldname" class="shrink-0 text-ink-green-5">✓ {{ __('Saved') }}</span>
            </div>
            <div
              v-if="f.read_only"
              class="flex h-7 items-center truncate text-sm text-ink-gray-8"
              :title="f.value || ''"
            >
              {{ f.value || '—' }}
            </div>
            <select
              v-else-if="f.fieldtype == 'Select'"
              v-model="quickValues[f.fieldname]"
              class="h-7 w-full rounded border border-outline-gray-2 bg-surface-white px-2 py-0 text-sm text-ink-gray-8"
              @change="saveQuick(f)"
            >
              <option v-for="o in f.options" :key="o" :value="o">{{ o }}</option>
            </select>
            <TextInput
              v-else
              v-model="quickValues[f.fieldname]"
              variant="outline"
              size="sm"
              :type="f.fieldtype == 'Int' ? 'number' : 'text'"
              @focus="editingField = f.fieldname"
              @blur="saveQuick(f)"
              @keydown.enter="(e) => e.target.blur()"
            />
          </div>
        </div>
        <div
          ref="threadEl"
          class="wa-wallpaper flex-1 overflow-y-auto px-4 py-4 transition-opacity duration-150 sm:px-12"
          :class="switching ? 'opacity-50' : ''"
        >
          <WhatsAppArea
            v-if="thread.data?.length"
            chat
            v-model="thread"
            v-model:reply="reply"
            :messages="thread.data"
          />
        </div>
        <div class="wa-bar border-t">
          <div
            v-if="conversation.data.blocked"
            class="flex items-center justify-between gap-2 px-3 py-3 sm:px-10"
          >
            <span class="text-sm text-ink-gray-5">{{ blockedText }}</span>
            <Button :label="__('Unblock')" :loading="blocking" @click="unblockNumber" />
          </div>
          <div
            v-else-if="!conversation.data.can_send"
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
            <!-- right padding keeps the send button clear of floating launchers (e.g. "Ask Mona") -->
            <div class="flex items-end gap-2 py-2.5 pl-3 pr-3 sm:pl-10 sm:pr-36">
              <FileUploader @success="(file) => sendFile(file)">
                <template #default="{ openFileSelector }">
                  <Dropdown :options="uploadOptions(openFileSelector)">
                    <Button variant="ghost" icon="plus" />
                  </Dropdown>
                </template>
              </FileUploader>
              <template v-if="conversation.data.can_draft">
                <Button
                  variant="ghost"
                  :loading="drafting"
                  :title="
                    content.trim()
                      ? __('Mona writes the message from what you typed (a draft or an instruction). You review and send it.')
                      : __('Draft a reply with Mona (you review and send it)')
                  "
                  @click="draftReply()"
                >
                  <template #icon><span aria-hidden="true">✨</span></template>
                </Button>
                <Dropdown :options="languageOptions">
                  <Button
                    variant="ghost"
                    icon="globe"
                    :disabled="drafting"
                    :title="__('Mona writes it in the language you pick')"
                  />
                </Dropdown>
                <Button
                  v-if="beforeMona !== null"
                  variant="ghost"
                  icon="rotate-ccw"
                  :title="__('Bring back what you typed')"
                  @click="undoDraft"
                />
              </template>
              <Textarea
                v-model="content"
                variant="outline"
                class="wa-input min-h-8 w-full"
                :rows="rows"
                :placeholder="
                  conversation.data.can_draft
                    ? __('Type your message, or a draft or instruction for Mona and press ✨')
                    : __('Type your message here...')
                "
                @focus="rows = 4"
                @blur="rows = content ? 4 : 1"
                @keydown.enter.exact.prevent="sendText"
              />
              <Button
                variant="solid"
                theme="green"
                class="!rounded-full"
                icon="send"
                :title="__('Send')"
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
      :reference-doctype="conversation.data?.reference_doctype || ''"
      :reference-name="conversation.data?.reference_name || ''"
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
  Avatar,
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
import { computed, reactive, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { createDialog } from '@/utils/dialogs'
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
const drafting = ref(false)
const beforeMona = ref(null) // what the rep had typed before Mona replaced it, for Undo
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

// Chats already opened in this visit are kept, so going back to one shows it at once while it refreshes quietly.
// A chat opened for the first time keeps the previous one on screen, slightly dimmed, until its data arrives:
// nothing blanks or jumps. An answer for a chat that is no longer the selected one is asked again.
const seen = new Map()
const switching = ref(false)
function remember(name, part, data) {
  seen.set(name, { ...(seen.get(name) || {}), [part]: data })
  if (seen.size > 40) seen.delete(seen.keys().next().value)
}

const conversation = createResource({
  url: 'crm.api.whatsapp_inbox.get_conversation',
  makeParams: () => ({ conversation: selected.value }),
  onSuccess: (data) => {
    if (data?.name !== selected.value) return selected.value && conversation.reload()
    remember(data.name, 'conversation', data)
  },
})

const thread = createResource({
  url: 'crm.api.whatsapp_inbox.get_thread',
  makeParams: () => ({ conversation: selected.value }),
  transform: (data) =>
    data.sort((a, b) => new Date(a.creation) - new Date(b.creation)),
  onSuccess: (data) => {
    const asked = thread.params?.conversation
    if (asked && asked !== selected.value) return selected.value && thread.reload()
    if (asked) remember(asked, 'thread', data)
    switching.value = false
    nextTick(scrollToEnd)
  },
  onError: () => (switching.value = false),
})

watch([scope, search, unreadOnly, status], () => conversations.reload())

// Lead details beside the chat: staff fill them in while talking. Saved when the cursor leaves the box or on Enter.
const showDetails = ref(false)
const quickValues = reactive({})
const editingField = ref(null)
const savedField = ref(null)
const quickFields = computed(() => conversation.data?.quick_fields || [])
watch(quickFields, (fields) => {
  for (const f of fields) {
    // a reload (each new message) must not wipe what is being typed
    if (editingField.value !== f.fieldname) quickValues[f.fieldname] = f.value ?? ''
  }
})

// "Ask": the ready question goes into the message box for the rep to send (after any text already there). The server
// remembers it was asked, so the assistant can fill the field from the customer's answer.
async function askQuick(f) {
  try {
    const out = await call('crm.api.whatsapp_inbox.ask_quick_field', {
      conversation: selected.value,
      fieldname: f.fieldname,
    })
    if (!out?.question) return
    const typed = content.value.trim()
    content.value = typed ? typed + '\n' + out.question : out.question
    rows.value = 4
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not get the question'))
  }
}

async function saveQuick(f) {
  editingField.value = null
  const value = quickValues[f.fieldname] ?? ''
  if (String(value).trim() === String(f.value ?? '').trim()) return
  const conversationName = selected.value
  try {
    const out = await call('crm.api.whatsapp_inbox.set_quick_field', {
      conversation: conversationName,
      fieldname: f.fieldname,
      value,
    })
    if (selected.value !== conversationName) return
    f.value = out.value
    quickValues[f.fieldname] = out.value ?? ''
    savedField.value = f.fieldname
    setTimeout(() => {
      if (savedField.value === f.fieldname) savedField.value = null
    }, 2000)
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save {0}', [f.label]))
    if (selected.value === conversationName) quickValues[f.fieldname] = f.value ?? ''
  }
}

function load() {
  if (!selected.value) return
  const kept = seen.get(selected.value)
  if (kept?.conversation && kept?.thread) {
    conversation.setData(kept.conversation)
    thread.setData(kept.thread)
    switching.value = false
    nextTick(scrollToEnd)
  } else {
    switching.value = Boolean(conversation.data)
  }
  conversation.reload()
  thread.reload()
  call('crm.api.whatsapp_inbox.mark_read', { conversation: selected.value }).then(
    () => refreshWhatsappUnread(),
  )
}

watch(
  selected,
  (name) => {
    // the page is no longer rebuilt per chat: nothing typed or picked for one chat may carry over to the next
    reply.value = {}
    beforeMona.value = null
    content.value = ''
    showTemplates.value = false
    if ((route.query.c || null) !== (name || null)) router.replace({ query: name ? { c: name } : {} })
    load()
  },
  { immediate: true },
)
// Back / Forward, or a link to another chat while the inbox is open
watch(
  () => route.query.c,
  (c) => {
    if (route.name === 'WhatsApp' && (c || null) !== (selected.value || null)) selected.value = c || null
  },
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
  if (ref.doctype === 'Contact') {
    router.push({ name: 'Contact', params: { contactId: ref.name } })
    return
  }
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
  beforeMona.value = null
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

// Mona writes the reply. Text already in the box goes to her as the rep's draft or instruction; a language picked
// from the menu is the language she writes in (none: the customer's language, or the one the instruction names).
const draftLanguages = ['English', 'Bangla', 'Banglish', 'Arabic', 'Hindi', 'Urdu']
const languageOptions = [
  { label: __("Customer's language"), onClick: () => draftReply() },
  ...draftLanguages.map((language) => ({
    label: __(language),
    onClick: () => draftReply(language),
  })),
]

async function draftReply(language) {
  if (drafting.value) return
  const typed = content.value.trim()
  const conversationName = selected.value
  drafting.value = true
  try {
    const out = await call('crm.api.whatsapp_inbox.draft_reply', {
      conversation: conversationName,
      language: language || null,
      instruction: typed || null,
    })
    // the rep moved to another chat, or kept typing, while Mona was writing: leave their box alone
    if (selected.value !== conversationName || content.value.trim() !== typed) return
    if (out?.reply) {
      beforeMona.value = typed ? content.value : null
      content.value = out.reply
      rows.value = 4
    }
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not draft a reply'))
  } finally {
    drafting.value = false
  }
}

function undoDraft() {
  content.value = beforeMona.value
  beforeMona.value = null
}

function sendTemplate(template) {
  showTemplates.value = false
  send('send_template', typeof template === 'object' ? template : { template })
}

async function setHandler(handler) {
  try {
    await call('crm.api.whatsapp_inbox.set_handler', { conversation: selected.value, handler })
    toast.success(handler == 'Mona' ? __('Mona answers this chat again') : __('You have this chat now'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not change who answers'))
  }
  conversation.reload()
}

// Block an abusive or spam sender: WhatsApp stops delivering their messages to this number, the chat is closed and
// apps follow up (hook crm_whatsapp_blocked, e.g. the lead goes to Junk).
const blocking = ref(false)
const blockedText = computed(() => {
  const d = conversation.data || {}
  const who = d.blocked_by_name || __('a colleague')
  return d.blocked_on_whatsapp
    ? __('Blocked by {0}. This number can no longer message us on WhatsApp.', [who])
    : __(
        'Blocked by {0} in the CRM only (WhatsApp: {1}). New messages from this number are kept silently: no unread mark, no task, no reply.',
        [who, d.block_note || __('not blocked there')],
      )
})

function blockNumber() {
  createDialog({
    title: __('Block this number?'),
    message: __(
      '+{0} will no longer be able to message this WhatsApp number. The chat is closed and its lead is marked as spam. You can unblock it later.',
      [conversation.data.contact_number],
    ),
    size: 'sm',
    actions: [
      { label: __('Cancel'), onClick: ({ close }) => close() },
      {
        label: __('Block'),
        variant: 'solid',
        theme: 'red',
        onClick: async ({ close }) => {
          try {
            const out = await call('crm.api.whatsapp_inbox.block', { conversation: selected.value })
            if (out?.on_whatsapp) toast.success(__('Number blocked'))
            else toast.warning(__('Blocked in the CRM only. WhatsApp did not block it: {0}', [out?.error || '']))
          } catch (e) {
            toast.error(e.messages?.[0] || __('Could not block the number'))
          }
          close()
          conversation.reload()
          conversations.reload()
          refreshWhatsappUnread()
        },
      },
    ],
  })
}

async function unblockNumber() {
  blocking.value = true
  try {
    await call('crm.api.whatsapp_inbox.unblock', { conversation: selected.value })
    toast.success(__('Number unblocked'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not unblock the number'))
  } finally {
    blocking.value = false
  }
  conversation.reload()
  conversations.reload()
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

<style>
/* WhatsApp's look for the open chat: beige wallpaper, grey top and bottom bars, a rounded white message box */
.wa-pane {
  --wa-wall: #efeae2;
  --wa-dot: rgba(17, 27, 33, 0.045);
  --wa-bar: #f0f2f5;
}
[data-theme='dark'] .wa-pane {
  --wa-wall: #0b141a;
  --wa-dot: rgba(255, 255, 255, 0.035);
  --wa-bar: #202c33;
}
.wa-pane .wa-wallpaper {
  background-color: var(--wa-wall);
  background-image: radial-gradient(var(--wa-dot) 1.5px, transparent 1.5px),
    radial-gradient(var(--wa-dot) 1.5px, transparent 1.5px);
  background-size: 28px 28px;
  background-position: 0 0, 14px 14px;
}
.wa-pane .wa-bar {
  background: var(--wa-bar);
}
.wa-pane .wa-input textarea {
  border-radius: 1.25rem;
  padding-left: 0.9rem;
  padding-right: 0.9rem;
}
</style>

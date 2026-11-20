<!-- eslint-disable vue/no-v-html -->
<template>
  <div :class="chat ? 'wa-chat' : ''">
    <template v-for="(whatsapp, index) in messages" :key="whatsapp.name">
    <div v-if="chat && newDay(index)" class="mb-3 mt-1 flex justify-center">
      <span class="wa-chip rounded-md px-3 py-1 text-xs shadow-sm">
        {{ dayLabel(whatsapp.creation) }}
      </span>
    </div>
    <div
      class="activity group flex gap-2"
      :class="[
        whatsapp.type == 'Outgoing' ? 'flex-row-reverse' : '',
        whatsapp.reaction ? 'mb-7' : chat ? (sameSender(index + 1) ? 'mb-0.5' : 'mb-2.5') : 'mb-3',
      ]"
    >
      <div
        :id="whatsapp.name"
        class="group/message relative text-base shadow-sm"
        :class="
          chat
            ? [
                'wa-bubble max-w-[85%] rounded-lg px-2 pb-1 pt-1.5 sm:max-w-[65%]',
                whatsapp.type == 'Outgoing' ? 'wa-out' : 'wa-in',
                sameSender(index) && !newDay(index) ? '' : 'wa-tail',
              ]
            : 'max-w-[90%] rounded-md bg-surface-gray-1 p-1.5 pl-2 text-ink-gray-9'
        "
      >
        <Badge
          v-if="whatsapp.status == 'failed' && !chat"
          theme="red"
          :label="whatsapp.status"
          class="absolute -top-2 right-0"
        />
        <div
          v-if="whatsapp.is_reply"
          class="mb-1 cursor-pointer rounded border-0 border-l-4 bg-surface-gray-3 p-2 text-ink-gray-5"
          :class="
            whatsapp.reply_to_type == 'Incoming'
              ? 'border-green-500'
              : 'border-blue-400'
          "
          @click="() => scrollToMessage(whatsapp.reply_to)"
        >
          <div
            class="mb-1 text-sm-bold"
            :class="
              whatsapp.reply_to_type == 'Incoming'
                ? 'text-ink-green-5'
                : 'text-ink-blue-link'
            "
          >
            {{ whatsapp.reply_to_from || __('You') }}
          </div>
          <div class="flex flex-col gap-2 max-h-12 overflow-hidden">
            <div v-if="whatsapp.header" class="text-base-semibold">
              {{ whatsapp.header }}
            </div>
            <div v-html="formatWhatsAppMessage(whatsapp.reply_message)" />
            <div v-if="whatsapp.footer" class="text-xs text-ink-gray-5">
              {{ whatsapp.footer }}
            </div>
          </div>
        </div>
        <div :class="chat ? 'flex flex-wrap items-end justify-end gap-x-2' : 'flex gap-2 justify-between'">
          <div
            v-if="whatsapp.status != 'failed'"
            class="absolute -right-0.5 -top-0.5 z-10 flex cursor-pointer gap-1 rounded-full pb-2 pl-2 pr-1.5 pt-1.5 opacity-0 group-hover/message:opacity-100"
            :class="chat ? 'wa-menu' : 'bg-surface-base'"
            :style="
              chat
                ? {}
                : {
                    background:
                      'radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 1) 0%, rgba(255, 255, 255, 1) 35%, rgba(238, 130, 238, 0) 100%)',
                  }
            "
          >
            <Dropdown :options="messageOptions(whatsapp)">
              <span
                class="lucide-chevron-down size-4 text-ink-gray-5"
                aria-hidden="true"
              />
            </Dropdown>
          </div>
          <div
            v-if="whatsapp.reaction"
            class="absolute -bottom-5 flex gap-1 rounded-full border bg-surface-base p-1 pb-[3px] shadow-sm"
          >
            <div class="flex size-4 items-center justify-center">
              {{ whatsapp.reaction }}
            </div>
          </div>
          <div
            v-if="whatsapp.message_type == 'Template'"
            class="flex flex-col gap-2"
            :class="chat ? 'min-w-0 grow' : ''"
          >
            <div v-if="whatsapp.header" class="text-base-semibold">
              {{ whatsapp.header }}
            </div>
            <div v-html="formatWhatsAppMessage(whatsapp.template)" />
            <div v-if="whatsapp.footer" class="text-xs text-ink-gray-5">
              {{ whatsapp.footer }}
            </div>
          </div>
          <div
            v-else-if="whatsapp.content_type == 'text'"
            :class="chat ? 'min-w-0 grow' : ''"
            v-html="formatWhatsAppMessage(whatsapp.message)"
          />
          <div
            v-else-if="whatsapp.content_type == 'button'"
            :class="chat ? 'min-w-0 grow' : ''"
            v-html="formatWhatsAppMessage(whatsapp.message)"
          />
          <div v-else-if="whatsapp.content_type == 'image'" :class="chat ? 'basis-full' : ''">
            <img
              :src="whatsapp.attach"
              class="cursor-pointer rounded-md"
              :class="chat ? 'max-h-80 max-w-full sm:max-w-xs' : 'h-40'"
              @click="() => openFileInAnotherTab(whatsapp.attach)"
            />
            <div
              v-if="caption(whatsapp)"
              class="mt-1.5"
              v-html="formatWhatsAppMessage(whatsapp.message)"
            />
          </div>
          <div
            v-else-if="whatsapp.content_type == 'document'"
            class="flex items-center gap-2"
            :class="chat ? 'wa-file basis-full cursor-pointer rounded-md p-2' : ''"
            @click="() => chat && openFileInAnotherTab(whatsapp.attach)"
          >
            <DocumentIcon
              class="cursor-pointer rounded-md text-ink-gray-4"
              :class="chat ? 'size-8 shrink-0' : 'size-10'"
              @click.stop="() => openFileInAnotherTab(whatsapp.attach)"
            />
            <div v-if="chat" class="min-w-0 truncate">{{ fileName(whatsapp.attach) }}</div>
            <div v-else class="text-ink-gray-5">Document</div>
          </div>
          <div
            v-else-if="whatsapp.content_type == 'audio'"
            class="flex items-center gap-2"
          >
            <audio :src="whatsapp.attach" controls class="cursor-pointer" />
          </div>
          <div
            v-else-if="whatsapp.content_type == 'video'"
            class="flex-col items-center gap-2"
          >
            <video
              :src="whatsapp.attach"
              controls
              class="h-40 cursor-pointer rounded-md"
            />
            <div
              v-if="caption(whatsapp)"
              class="mt-1.5"
              v-html="formatWhatsAppMessage(whatsapp.message)"
            />
          </div>
          <div
            class="flex shrink-0 items-end gap-1"
            :class="chat ? 'wa-meta -mb-0.5 ml-auto' : '-mb-1 text-ink-gray-5'"
          >
            <span
              v-if="chat && whatsapp.status == 'failed'"
              class="text-2xs font-medium text-ink-red-4"
              :title="__('WhatsApp did not deliver this message')"
            >
              ⚠ {{ __('Not sent') }}
            </span>
            <Tooltip :text="formatDate(whatsapp.creation, 'ddd, MMM D, YYYY')">
              <div class="text-2xs">
                {{ formatDate(whatsapp.creation, 'hh:mm a') }}
              </div>
            </Tooltip>
            <div v-if="whatsapp.type == 'Outgoing'">
              <CheckIcon
                v-if="['sent', 'Success'].includes(whatsapp.status)"
                class="size-4"
              />
              <DoubleCheckIcon
                v-else-if="['read', 'delivered'].includes(whatsapp.status)"
                class="size-4"
                :class="
                  whatsapp.status == 'read' ? (chat ? 'wa-read' : 'text-ink-blue-5') : ''
                "
              />
            </div>
          </div>
        </div>
      </div>
      <div
        v-if="whatsapp.status != 'failed'"
        class="flex items-center justify-center opacity-0 transition-all ease-in group-hover:opacity-100"
      >
        <IconPicker
          v-slot="{ togglePopover }"
          v-model="emoji"
          v-model:reaction="reaction"
          @update:modelValue="() => reactOnMessage(whatsapp.name, emoji)"
        >
          <Button
            class="rounded-full !size-6 mt-0.5"
            @click="() => (reaction = true) && togglePopover()"
          >
            <template #icon>
              <ReactIcon class="text-ink-gray-3" />
            </template>
          </Button>
        </IconPicker>
      </div>
    </div>
    </template>
  </div>
</template>

<script setup>
import IconPicker from '@/components/IconPicker.vue'
import CheckIcon from '@/components/Icons/CheckIcon.vue'
import DoubleCheckIcon from '@/components/Icons/DoubleCheckIcon.vue'
import DocumentIcon from '@/components/Icons/DocumentIcon.vue'
import ReactIcon from '@/components/Icons/ReactIcon.vue'
import { formatDate, sanitizeHTML } from '@/utils'
import { useTelemetry } from 'frappe-ui/frappe'
import { Tooltip, Dropdown, createResource, toast } from 'frappe-ui'
import { ref } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  // WhatsApp's own look: coloured bubbles with tails, day separators, time and ticks at the bottom right
  chat: { type: Boolean, default: false },
})

// is message `index` from the same side as the one before it (a run of bubbles shares one tail)
function sameSender(index) {
  const current = props.messages[index]
  return index > 0 && Boolean(current) && current.type === props.messages[index - 1].type
}

function day(dt) {
  return formatDate(dt, 'YYYY-MM-DD')
}

function newDay(index) {
  return index === 0 || day(props.messages[index].creation) !== day(props.messages[index - 1].creation)
}

function dayLabel(dt) {
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86400000)
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (day(dt) === iso(today)) return __('Today')
  if (day(dt) === iso(yesterday)) return __('Yesterday')
  return formatDate(dt, 'D MMMM YYYY')
}

// a media message with no caption carries its own file path as the text
function caption(message) {
  const text = message.message || ''
  return text && !text.startsWith('/files/') && !text.startsWith('/private/files/')
}

function fileName(url) {
  return decodeURIComponent((url || '').split('?')[0].split('/').pop() || '') || __('Document')
}

const list = defineModel({ type: Object })

const { capture } = useTelemetry()

function openFileInAnotherTab(url) {
  window.open(url, '_blank')
}

function formatWhatsAppMessage(message) {
  // if message contains _text_, make it italic
  message = message.replace(/_(.*?)_/g, '<i>$1</i>')
  // if message contains *text*, make it bold
  message = message.replace(/\*(.*?)\*/g, '<b>$1</b>')
  // if message contains ~text~, make it strikethrough
  message = message.replace(/~(.*?)~/g, '<s>$1</s>')
  // if message contains ```text```, make it monospace
  message = message.replace(/```(.*?)```/g, '<code>$1</code>')
  // if message contains `text`, make it inline code
  message = message.replace(/`(.*?)`/g, '<code>$1</code>')
  // if message contains > text, make it a blockquote
  message = message.replace(/^> (.*)$/gm, '<blockquote>$1</blockquote>')
  // if contain /n, make it a new line
  message = message.replace(/\n/g, '<br>')
  // if contains *<space>text, make it a bullet point
  message = message.replace(/\* (.*?)(?=\s*\*|$)/g, '<li>$1</li>')
  message = message.replace(/- (.*?)(?=\s*-|$)/g, '<li>$1</li>')
  message = message.replace(/(\d+)\. (.*?)(?=\s*(\d+)\.|$)/g, '<li>$2</li>')

  return sanitizeHTML(message)
}

const emoji = ref('')
const reaction = ref(true)

function reactOnMessage(name, emoji) {
  createResource({
    url: 'crm.api.whatsapp.react_on_whatsapp_message',
    params: {
      emoji,
      reply_to_name: name,
    },
    auto: true,
    onSuccess() {
      capture('whatsapp_react_on_message')
      list.value.reload()
    },
    onError(error) {
      toast.error(
        error.messages?.[0] || __('Failed to add reaction to the message'),
      )
    },
  })
}

const reply = defineModel('reply', { type: Object, default: () => ({}) })
const replyMode = ref(false)

function messageOptions(message) {
  return [
    {
      label: 'Reply',
      onClick: () => {
        replyMode.value = true
        reply.value = {
          ...message,
          message: formatWhatsAppMessage(message.message),
        }
      },
    },
    // {
    //   label: 'Forward',
    //   onClick: () => console.log('Forward'),
    // },
    // {
    //   label: 'Delete',
    //   onClick: () => console.log('Delete'),
    // },
  ]
}

function scrollToMessage(name) {
  const element = document.getElementById(name)
  element.scrollIntoView({ behavior: 'smooth' })

  // Highlight the message
  element.classList.add('bg-yellow-100')
  setTimeout(() => {
    element.classList.remove('bg-yellow-100')
  }, 1000)
}
</script>

<style>
.wa-chat {
  --wa-in: #ffffff;
  --wa-out: #d9fdd3;
  --wa-text: #111b21;
  --wa-meta: #667781;
  --wa-chip: #ffffff;
  --wa-file: rgba(17, 27, 33, 0.06);
  --wa-read: #53bdeb;
}
[data-theme='dark'] .wa-chat {
  --wa-in: #202c33;
  --wa-out: #005c4b;
  --wa-text: #e9edef;
  --wa-meta: #9fb0b9;
  --wa-chip: #182229;
  --wa-file: rgba(255, 255, 255, 0.08);
}
.wa-chat .wa-bubble {
  color: var(--wa-text);
  overflow-wrap: anywhere;
}
.wa-chat .wa-in {
  background: var(--wa-in);
}
.wa-chat .wa-out {
  background: var(--wa-out);
}
/* the little tail on the first bubble of a run */
.wa-chat .wa-tail.wa-in {
  border-top-left-radius: 0;
}
.wa-chat .wa-tail.wa-out {
  border-top-right-radius: 0;
}
.wa-chat .wa-tail::before {
  content: '';
  position: absolute;
  top: 0;
  border-style: solid;
  border-width: 0 8px 10px 8px;
  border-color: transparent;
}
.wa-chat .wa-tail.wa-in::before {
  left: -8px;
  border-right-color: var(--wa-in);
  border-width: 0 8px 10px 0;
}
.wa-chat .wa-tail.wa-out::before {
  right: -8px;
  border-left-color: var(--wa-out);
  border-width: 0 0 10px 8px;
}
.wa-chat .wa-meta {
  color: var(--wa-meta);
}
.wa-chat .wa-read {
  color: var(--wa-read);
}
.wa-chat .wa-chip {
  background: var(--wa-chip);
  color: var(--wa-meta);
}
.wa-chat .wa-file {
  background: var(--wa-file);
}
.wa-chat .wa-in .wa-menu {
  background: radial-gradient(circle at 50% 50%, var(--wa-in) 35%, transparent 100%);
}
.wa-chat .wa-out .wa-menu {
  background: radial-gradient(circle at 50% 50%, var(--wa-out) 35%, transparent 100%);
}
.wa-chat .wa-bubble a {
  color: #027eb5;
  text-decoration: underline;
}
[data-theme='dark'] .wa-chat .wa-bubble a {
  color: #53bdeb;
}
</style>

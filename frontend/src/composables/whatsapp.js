import { createResource } from 'frappe-ui'
import { ref } from 'vue'

export const whatsappEnabled = ref(false)
export const isWhatsappInstalled = ref(false)

createResource({
  url: 'crm.api.whatsapp.is_whatsapp_enabled',
  cache: 'Is Whatsapp Enabled',
  auto: true,
  onSuccess: (data) => {
    whatsappEnabled.value = Boolean(data)
  },
})

createResource({
  url: 'crm.api.whatsapp.is_whatsapp_installed',
  cache: 'Is Whatsapp Installed',
  auto: true,
  onSuccess: (data) => {
    isWhatsappInstalled.value = Boolean(data)
  },
})

// unread WhatsApp conversations the user can see (sidebar badge); refreshed by the inbox and on "whatsapp_inbox" events
export const whatsappUnread = ref(0)

const whatsappUnreadResource = createResource({
  url: 'crm.api.whatsapp_inbox.unread_count',
  onSuccess: (data) => {
    whatsappUnread.value = Number(data) || 0
  },
})

export function refreshWhatsappUnread() {
  if (isWhatsappInstalled.value) whatsappUnreadResource.reload()
}

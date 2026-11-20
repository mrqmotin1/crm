<template>
  <Dialog v-model:open="show" size="7xl" bare>
    <div class="flex h-[88vh] flex-col overflow-hidden">
      <div class="flex items-center justify-end gap-1 border-b px-2 py-1">
        <Button
          variant="ghost"
          size="sm"
          icon-left="external-link"
          :label="__('Details')"
          @click="openDetails"
        />
        <Button
          variant="ghost"
          size="sm"
          icon="x"
          :aria-label="__('Close')"
          @click="show = false"
        />
      </div>
      <div class="crm-card-modal-page flex min-h-0 flex-1 flex-col">
        <component :is="page" v-bind="pageProps" />
      </div>
    </div>
  </Dialog>
</template>

<script setup>
// A kanban card opened in place (Trello-style): the real Lead / Deal page, with its
// header rendered inline (LayoutHeader reads `inlineLayoutHeader`), so the status
// flow, assignment, activities and fields behave exactly as on the full page.
import { Dialog } from 'frappe-ui'
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, provide, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
})
const emit = defineEmits(['close'])
const show = defineModel({ type: Boolean, default: true })
const router = useRouter()

provide('inlineLayoutHeader', true)

const PAGES = {
  'CRM Lead': {
    component: defineAsyncComponent(() => import('@/pages/Lead.vue')),
    prop: 'leadId',
    route: 'Lead',
  },
  'CRM Deal': {
    component: defineAsyncComponent(() => import('@/pages/Deal.vue')),
    prop: 'dealId',
    route: 'Deal',
  },
}

const page = computed(() => PAGES[props.doctype].component)
const pageProps = computed(() => ({ [PAGES[props.doctype].prop]: props.name }))

// Closing must be instant. The dialog's own fade-out runs while the whole Lead/Deal page inside it is torn down;
// on a slower computer that work freezes the fade half-way for seconds (a ghost of the card over the board). So the
// dialog is taken off the screen at once, without the fade (`crm-card-closing` on <body>, styled below), the
// browser paints the board, and only then `close` runs (route change, teardown, board refresh).
const CLOSING = 'crm-card-closing'
let alive = true
let safety = null
function shown() {
  clearTimeout(safety)
  document.body.classList.remove(CLOSING)
}
onMounted(shown) // a card opened right after another was closed must show
onBeforeUnmount(() => {
  alive = false
  clearTimeout(safety)
  safety = setTimeout(shown, 100) // the dialog's elements are removed with this component
})
watch(
  show,
  (open) => {
    if (open) return
    document.body.classList.add(CLOSING)
    safety = setTimeout(shown, 3000) // never leave dialogs hidden if something goes wrong below
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        if (alive) emit('close') // not if another card was opened meanwhile (this one is already gone)
      }),
    )
  },
  { flush: 'sync' },
)

function openDetails() {
  const p = PAGES[props.doctype]
  router.push({ name: p.route, params: { [p.prop]: props.name } })
}
</script>

<style>
/* A closing card disappears at once (see the script): no fade, nothing left over the board. */
body.crm-card-closing .dialog-overlay,
body.crm-card-closing .dialog-scroll-container {
  display: none !important;
}
/* The page's body is `h-full`; inside the modal it shares the column with its header. */
.crm-card-modal-page > .h-full {
  flex: 1 1 0%;
  height: auto;
  min-height: 0;
}
</style>

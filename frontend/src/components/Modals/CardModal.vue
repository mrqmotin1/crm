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
import { computed, defineAsyncComponent, provide, watch } from 'vue'
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

watch(show, (open) => {
  if (!open) emit('close')
})

function openDetails() {
  const p = PAGES[props.doctype]
  router.push({ name: p.route, params: { [p.prop]: props.name } })
}
</script>

<style>
/* The page's body is `h-full`; inside the modal it shares the column with its header. */
.crm-card-modal-page > .h-full {
  flex: 1 1 0%;
  height: auto;
  min-height: 0;
}
</style>

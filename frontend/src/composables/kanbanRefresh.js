import { globalStore } from '@/stores/global'
import { onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'

// Server event `crm_kanban_refresh` ({ doctype, name }): something outside the board changed a card (e.g. a WhatsApp
// message came in or was read). The open board reloads quietly; several events in a row make one reload. Not while
// a card is open (closing it reloads) or being dragged.
export function useKanbanRefresh(doctype, list) {
  const { $socket } = globalStore()
  const route = useRoute()
  let timer = null

  function reload(tries = 0) {
    if (route.params.viewType !== 'kanban' || route.query.card) return
    if (document.querySelector('.sortable-chosen') && tries < 20) {
      timer = setTimeout(() => reload(tries + 1), 1000)
      return
    }
    list.value?.reload?.()
  }

  function onRefresh(data) {
    if (data?.doctype !== doctype || route.params.viewType !== 'kanban') return
    clearTimeout(timer)
    timer = setTimeout(reload, 800)
  }

  onMounted(() => $socket?.on('crm_kanban_refresh', onRefresh))
  onBeforeUnmount(() => {
    clearTimeout(timer)
    $socket?.off('crm_kanban_refresh', onRefresh)
  })
}

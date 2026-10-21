<template>
  <div ref="el" class="flex min-h-0 flex-1 flex-col" />
</template>
<script setup>
// The panel of a tab registered by another app (see data/extensions.js).
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  tab: { type: Object, required: true },
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})
const emit = defineEmits(['reload'])
const el = ref(null)
const router = useRouter()
let cleanup = null

onMounted(() => {
  try {
    cleanup = props.tab.mount(el.value, {
      doctype: props.doctype,
      docname: props.docname,
      reload: () => emit('reload'),
      router,
    })
  } catch (e) {
    console.error(`Tab ${props.tab.name} failed to load`, e)
  }
})
onBeforeUnmount(() => typeof cleanup === 'function' && cleanup())
</script>

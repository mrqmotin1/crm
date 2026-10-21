import { h, markRaw, reactive } from 'vue'

// Tabs that other apps add to the Lead / Deal pages, from a script listed in their `crm_include_js` hook:
//   window.crmApi.registerTab({
//     name: 'Mona', label: 'Mona', icon: '<svg ...>', doctypes: ['CRM Lead', 'CRM Deal'], position: 1,
//     mount(el, { doctype, docname, reload, router }) { ...render into el...; return () => { ...cleanup... } },
//   })
// The tab panel is the app's own DOM: the CRM only shows the tab and calls mount / cleanup.
export const extensionTabs = reactive([])

export function registerTab(tab) {
  if (!tab?.name || typeof tab.mount !== 'function') return
  const i = extensionTabs.findIndex((t) => t.name === tab.name)
  if (i >= 0) extensionTabs.splice(i, 1)
  extensionTabs.push(markRaw(tab))
}

const icons = new WeakMap()
function iconOf(tab) {
  if (!tab.icon) return undefined
  if (!icons.has(tab)) {
    icons.set(
      tab,
      markRaw({
        render: () =>
          h('span', { class: 'inline-flex size-4 items-center justify-center [&>svg]:size-4', innerHTML: tab.icon }),
      }),
    )
  }
  return icons.get(tab)
}

export function withExtensionTabs(doctype, tabs) {
  const out = [...tabs]
  for (const t of extensionTabs) {
    if (t.doctypes && !t.doctypes.includes(doctype)) continue
    const tab = { name: t.name, label: t.label || t.name, icon: iconOf(t), extension: t }
    out.splice(Math.min(t.position ?? out.length, out.length), 0, tab)
  }
  return out
}

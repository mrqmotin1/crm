import { createResource } from 'frappe-ui'

// Trello-like label colours: background + readable text, applied inline (no Tailwind safelist).
export const LABEL_COLORS = {
  green: { bg: '#4BCE97', fg: '#164B35' },
  yellow: { bg: '#F5CD47', fg: '#533F04' },
  orange: { bg: '#FEA362', fg: '#702E00' },
  red: { bg: '#F87168', fg: '#5D1F1A' },
  purple: { bg: '#9F8FEF', fg: '#352C63' },
  blue: { bg: '#579DFF', fg: '#09326C' },
  sky: { bg: '#6CC3E0', fg: '#164555' },
  lime: { bg: '#94C748', fg: '#37471F' },
  pink: { bg: '#E774BB', fg: '#50253F' },
  gray: { bg: '#8590A2', fg: '#FFFFFF' },
  black: { bg: '#44546F', fg: '#FFFFFF' },
}

let labels = null

export function labelsStore() {
  if (!labels) {
    labels = createResource({
      url: 'crm.api.labels.get_labels',
      cache: 'crm-labels',
      auto: true,
    })
  }

  function styleFor(color) {
    const c = LABEL_COLORS[color] || LABEL_COLORS.gray
    return { backgroundColor: c.bg, color: c.fg }
  }

  function colorOf(name) {
    return (labels.data || []).find((l) => l.name === name)?.color
  }

  return { labels, styleFor, colorOf }
}

export function parseLabels(value) {
  if (Array.isArray(value)) return value
  if (!value) return []
  try {
    const names = JSON.parse(value)
    return Array.isArray(names) ? names : []
  } catch {
    return []
  }
}

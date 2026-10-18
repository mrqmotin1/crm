// Trello-style kanban board backgrounds: a solid colour, a preset gradient (g:<name>) or an image URL.
export const BOARD_COLORS = ['#0079BF', '#D29034', '#519839', '#B04632', '#89609E', '#CD5A91', '#4BBF6B', '#00AECC', '#838C91', '#172B4D']

export const BOARD_GRADIENTS = {
  ocean: 'linear-gradient(135deg, #0C66E4 0%, #09326C 100%)',
  aurora: 'linear-gradient(135deg, #4BCE97 0%, #0C66E4 100%)',
  sunset: 'linear-gradient(135deg, #F9B04C 0%, #E2533F 100%)',
  peach: 'linear-gradient(135deg, #FEA362 0%, #E774BB 100%)',
  plum: 'linear-gradient(135deg, #9F8FEF 0%, #352C63 100%)',
  forest: 'linear-gradient(135deg, #216E4E 0%, #164B35 100%)',
}

export function boardBackgroundStyle(value) {
  if (!value) return {}
  if (value.startsWith('#')) return { background: value }
  if (value.startsWith('g:')) return { background: BOARD_GRADIENTS[value.slice(2)] || 'none' }
  return {
    backgroundImage: `url("${value.replace(/"/g, '%22')}")`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
  }
}

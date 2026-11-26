/** Small moments of delight. Everything here is skipped when the OS asks for reduced motion. */

const INK = ['#19a9ee', '#ec2f8c', '#ffd231', '#f0392e', '#7accf6', '#f78cc1', '#99a1ae', '#e6ebf3', '#3a4050', '#4c9bff']

function calm() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** Throw a spray of ink droplets from an element (or a click) — used when a print is sent. */
export function inkBurst(from: Element | { clientX: number; clientY: number } | null | undefined, count = 14) {
  if (!from || calm()) return
  let x: number, y: number
  if (from instanceof Element) {
    const r = from.getBoundingClientRect()
    x = r.left + r.width / 2
    y = r.top + r.height / 2
  } else {
    x = from.clientX
    y = from.clientY
  }
  for (let i = 0; i < count; i++) {
    const el = document.createElement('i')
    el.className = 'ink-drop'
    el.style.left = `${x}px`
    el.style.top = `${y}px`
    el.style.background = INK[i % INK.length]
    document.body.appendChild(el)
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.5
    const dist = 46 + Math.random() * 74
    const dx = Math.cos(angle) * dist
    const dy = Math.sin(angle) * dist
    const size = 0.6 + Math.random() * 0.9
    const spin = (Math.random() - 0.5) * 240
    el.animate(
      [
        { transform: `translate(0, 0) scale(${size * 0.4}) rotate(-45deg)`, opacity: 1 },
        { transform: `translate(${dx}px, ${dy}px) scale(${size}) rotate(${spin - 45}deg)`, opacity: 1, offset: 0.55 },
        { transform: `translate(${dx * 1.15}px, ${dy + 60 + Math.random() * 40}px) scale(${size * 0.5}) rotate(${spin - 45}deg)`, opacity: 0 },
      ],
      { duration: 780 + Math.random() * 320, easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)', delay: i * 8 },
    ).onfinish = () => el.remove()
  }
}

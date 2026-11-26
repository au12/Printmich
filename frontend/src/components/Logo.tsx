import { useId, useMemo } from 'react'
import markSvg from '../assets/logo-mark.svg?raw'

/**
 * The Printmich mark: ten ink tanks arched over a printer handing you a photo.
 * Drawn by dev/make_icons.py; inlined here so its parts (lm-tank, lm-arrow, lm-photo, lm-led)
 * can move. `intro` plays once on mount, `busy` loops while something is printing.
 */
export function Logo({ size = 36, intro, busy, wave, className }: { size?: number; intro?: boolean; busy?: boolean; wave?: boolean; className?: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  // Gradient ids must be unique per copy: a copy inside a hidden container can't paint the others.
  const html = useMemo(() => markSvg.replaceAll('id="lm-', `id="${uid}-`).replaceAll('url(#lm-', `url(#${uid}-`), [uid])
  const cls = ['logo', intro && 'intro', busy && 'busy', wave && 'wave', className].filter(Boolean).join(' ')
  return <span className={cls} aria-hidden="true" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: html }} />
}

import type { AssetSummary } from './types'

export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Photo capture dates come from EXIF local time; show them as written (no timezone shift). */
export function takenDate(a: Pick<AssetSummary, 'taken_at'> | null | undefined): Date | null {
  if (!a?.taken_at) return null
  const m = a.taken_at.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/)
  if (!m) return parseDate(a.taken_at)
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0))
}

export function fmtDate(d: Date | null, opts: Intl.DateTimeFormatOptions = { month: 'long', day: 'numeric', year: 'numeric' }) {
  return d ? d.toLocaleDateString(undefined, opts) : ''
}

export function fmtTime(d: Date | null) {
  return d ? d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : ''
}

export function fmtDateTime(s: string | null | undefined) {
  const d = parseDate(s)
  if (!d) return ''
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}, ${fmtTime(d)}`
}

export function relativeTime(s: string | null | undefined, now = new Date()): string {
  const d = parseDate(s)
  if (!d) return ''
  const diff = (d.getTime() - now.getTime()) / 1000
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (abs < 45) return diff >= 0 ? 'in a moment' : 'just now'
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), 'day')
  if (abs < 86400 * 60) return rtf.format(Math.round(diff / 604800), 'week')
  return rtf.format(Math.round(diff / (86400 * 30.4)), 'month')
}

/** "Tomorrow at 8:00 AM", "Today at 8:00 AM", "Friday at 8:00 AM", "Nov 30 at 8:00 AM" */
export function whenLabel(s: string | null | undefined): string {
  const d = parseDate(s)
  if (!d) return ''
  const now = new Date()
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const delta = Math.round((day(d) - day(now)) / 86400000)
  const t = fmtTime(d)
  if (delta === 0) return `Today at ${t}`
  if (delta === 1) return `Tomorrow at ${t}`
  if (delta > 1 && delta < 7) return `${d.toLocaleDateString(undefined, { weekday: 'long' })} at ${t}`
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} at ${t}`
}

export function place(a: AssetSummary | null | undefined): string {
  if (!a) return ''
  const city = (a.city || '').trim()
  const region = (a.state || a.country || '').trim()
  if (city && region && region.toLowerCase() !== city.toLowerCase()) return `${city}, ${region}`
  return city || region
}

export function photoTitle(a: AssetSummary | null | undefined): string {
  if (!a) return 'Test page'
  return a.description?.trim() || place(a) || a.filename || 'Untitled'
}

export function camera(a: AssetSummary): string {
  const make = (a.make || '').trim()
  const model = (a.model || '').trim()
  if (!model) return make
  if (make && model.toLowerCase().startsWith(make.split(' ')[0].toLowerCase())) return model
  return `${make} ${model}`.trim()
}

export function exposureParts(a: AssetSummary): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = []
  if (a.focal_length) out.push({ label: 'Focal length', value: `${round(a.focal_length, 1)} mm` })
  if (a.f_number) out.push({ label: 'Aperture', value: `ƒ/${round(a.f_number, 1)}` })
  if (a.exposure_time) out.push({ label: 'Shutter', value: a.exposure_time.endsWith('s') ? a.exposure_time : `${a.exposure_time} s` })
  if (a.iso) out.push({ label: 'ISO', value: String(a.iso) })
  return out
}

export function round(v: number, digits = 0) {
  const f = 10 ** digits
  return Math.round(v * f) / f
}

export function mm(v: number, units: 'in' | 'mm') {
  if (units === 'mm') return `${round(v, v < 10 ? 1 : 0)} mm`
  const inches = v / 25.4
  const q = Math.round(inches * 8) / 8
  return Math.abs(q - inches) < 0.02 ? `${fmtInches(q)}″` : `${round(inches, 2)}″`
}

function fmtInches(v: number) {
  const whole = Math.floor(v)
  const frac = v - whole
  const map: Record<string, string> = { '0.125': '⅛', '0.25': '¼', '0.375': '⅜', '0.5': '½', '0.625': '⅝', '0.75': '¾', '0.875': '⅞' }
  const f = map[String(round(frac, 3))]
  if (!frac) return String(whole)
  return f ? `${whole || ''}${f}` : String(round(v, 2))
}

export function money(v: number | null | undefined, currency = '$') {
  if (v == null) return ''
  return `${currency}${v.toFixed(2)}`
}

export const STATUS_TEXT: Record<string, string> = {
  queued: 'Queued',
  preparing: 'Preparing',
  rendering: 'Rendering',
  sending: 'Sending',
  printing: 'Printing',
  waiting: 'Waiting for printer',
  held: 'Held — check paper',
  completed: 'Printed',
  failed: 'Failed',
  canceled: 'Canceled',
}

export const ACTIVE_STATUSES = ['queued', 'preparing', 'rendering', 'sending', 'printing', 'waiting', 'held']

export function aspectOf(a: { width?: number | null; height?: number | null } | null | undefined, fallback = 1.5) {
  if (!a?.width || !a?.height) return fallback
  return a.width / a.height
}

export function plural(n: number, word: string, pluralWord = `${word}s`) {
  return `${n.toLocaleString()} ${n === 1 ? word : pluralWord}`
}

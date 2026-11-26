import type { CSSProperties } from 'react'
import type { InkTank, Marker } from '../lib/types'

/** The ten PRO-310 inks, in the order the tanks sit in the logo's arch. */
export const INKS = [
  { key: 'MBK', name: 'Matte Black', color: 'var(--ink-mbk)', hex: '#3a4050' },
  { key: 'PBK', name: 'Photo Black', color: 'var(--ink-pbk)', hex: '#14161c' },
  { key: 'GY', name: 'Gray', color: 'var(--ink-gy)', hex: '#99a1ae' },
  { key: 'C', name: 'Cyan', color: 'var(--ink-c)', hex: '#19a9ee' },
  { key: 'PC', name: 'Photo Cyan', color: 'var(--ink-pc)', hex: '#7accf6' },
  { key: 'M', name: 'Magenta', color: 'var(--ink-m)', hex: '#ec2f8c' },
  { key: 'PM', name: 'Photo Magenta', color: 'var(--ink-pm)', hex: '#f78cc1' },
  { key: 'Y', name: 'Yellow', color: 'var(--ink-y)', hex: '#ffd231' },
  { key: 'R', name: 'Red', color: 'var(--ink-r)', hex: '#f0392e' },
  { key: 'CO', name: 'Chroma Optimizer', color: 'var(--ink-co)', hex: '#e6ebf3' },
]

const INK_BY_KEY = Object.fromEntries(INKS.map((i) => [i.key, i]))
const isBlack = (key: string) => key === 'MBK' || key === 'PBK'
const idx = (i: number) => ({ ['--i' as string]: i }) as CSSProperties

/** The ten inks taking turns: Printmich's loading state. */
export function InkLoader({ label, inline }: { label?: string; inline?: boolean }) {
  return (
    <div className={`ink-loader${inline ? ' inline' : ''}`} role="status" aria-live="polite">
      <span className="bars" aria-hidden="true">
        {INKS.map((ink, i) => <i key={ink.key} className={isBlack(ink.key) ? 'blk' : ''} style={{ background: ink.color, ...idx(i) }} />)}
      </span>
      <span>{label ?? 'Loading'}…</span>
    </div>
  )
}

/** A thin bar the inks flow across while a job is in progress. */
export function InkProgress() {
  return (
    <div className="progress-ink" aria-hidden="true">
      {INKS.map((ink, i) => (
        <i key={ink.key} style={{ background: isBlack(ink.key) ? '#9a9a9a' : ink.color, ...idx(i) }} />
      ))}
    </div>
  )
}

function shortName(name: string) {
  const m = name.match(/^([A-Z]{1,3})\b/)
  if (m) return m[1]
  const words = name.replace(/ink|tank|cartridge|pfi-?\d+|pgi-?\d+/gi, '').trim().split(/\s+/)
  return words.map((w) => w[0]).join('').toUpperCase().slice(0, 3) || name.slice(0, 3)
}

type Level = { key: string; name: string; color: string; percent: number | null; status: 'ok' | 'low' | 'empty' | 'unknown'; title: string }

function levelsOf(markers: Marker[], tanks?: InkTank[]): Level[] {
  if (tanks?.length) {
    return tanks.map((t) => {
      const known = t.percent != null
      const pct = known ? Math.max(0, Math.min(100, t.percent!)) : null
      return {
        key: t.ink, name: t.name, color: INK_BY_KEY[t.ink]?.color ?? t.color, percent: pct, status: t.status,
        title: known ? `${t.name}: about ${t.level_ml?.toFixed(1)} ml (${Math.round(pct!)}%), estimated` : `${t.name}: not tracked yet`,
      }
    })
  }
  return markers.map((m) => {
    const pct = m.level < 0 ? null : Math.max(0, Math.min(100, (m.level / (m.high || 100)) * 100))
    const key = shortName(m.name)
    return {
      key, name: m.name, color: INK_BY_KEY[key]?.color ?? m.color, percent: pct,
      status: pct == null ? 'unknown' : m.level <= m.low ? 'low' : 'ok',
      title: `${m.name}: ${pct == null ? 'unknown' : `${Math.round(pct)}%`}`,
    }
  })
}

/** Ink levels as ten little tanks. Dashed outlines mean Printmich's estimate rather than the printer's reading. */
export function InkLevels({ markers, tanks }: { markers: Marker[]; tanks?: InkTank[] }) {
  const estimated = !!tanks?.length
  const levels = levelsOf(markers, tanks)
  if (!levels.length) return <div className="faint small">The printer doesn't report ink levels.</div>
  return (
    <div className={`ink-row${estimated ? ' est' : ''}`} role="list" aria-label={estimated ? 'Estimated ink levels' : 'Ink levels'}>
      {levels.map((l, i) => (
        <div className={`ink ${l.status}${isBlack(l.key) ? ' blk' : ''}`} key={`${l.key}-${i}`} role="listitem" title={l.title}>
          <div className="tank">
            <div className={`fill${l.status === 'low' || l.status === 'empty' ? ' low' : ''}`} style={{ height: `${l.percent ?? 0}%`, backgroundColor: l.color, ...idx(i) }} />
          </div>
          <span className="lbl">{l.key}</span>
        </div>
      ))}
    </div>
  )
}

/** The same levels at a glance, for the sidebar. */
export function MiniInk({ markers, tanks }: { markers: Marker[]; tanks?: InkTank[] }) {
  const levels = levelsOf(markers, tanks)
  if (!levels.some((l) => l.percent != null)) return null
  return (
    <span className="mini-ink" aria-hidden="true">
      {levels.map((l, i) => (
        <i key={`${l.key}-${i}`} title={l.title}>
          <b className={isBlack(l.key) ? 'blk' : ''} style={{ height: `${Math.max(6, l.percent ?? 0)}%`, background: l.status === 'empty' ? 'var(--err)' : l.color, ...idx(i) }} />
        </i>
      ))}
    </span>
  )
}

/** Estimated ink a print used, as one bar split by ink. */
export function InkUsage({ ink }: { ink: Record<string, number> }) {
  const parts = INKS.map((i) => ({ ...i, ml: ink[i.key] ?? 0 })).filter((p) => p.ml > 0)
  const total = parts.reduce((s, p) => s + p.ml, 0)
  if (!total) return null
  return (
    <span className="ink-usage" title={parts.map((p) => `${p.name} ${p.ml.toFixed(3)} ml`).join('\n')}>
      <span className="bar" aria-hidden="true">
        {parts.map((p) => <i key={p.key} style={{ width: `${(p.ml / total) * 100}%`, background: p.color }} />)}
      </span>
      <span className="num">≈ {total < 1 ? total.toFixed(2) : total.toFixed(1)} ml</span>
    </span>
  )
}

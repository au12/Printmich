import type { InkTank, Marker } from '../lib/types'

/** The ten PRO-310 inks — the only color the interface itself uses. */
export const INKS = [
  { key: 'MBK', name: 'Matte Black', color: 'var(--ink-mbk)', hex: '#2b2b2b' },
  { key: 'PBK', name: 'Photo Black', color: 'var(--ink-pbk)', hex: '#060606' },
  { key: 'GY', name: 'Gray', color: 'var(--ink-gy)', hex: '#8e8e8e' },
  { key: 'C', name: 'Cyan', color: 'var(--ink-c)', hex: '#00a3e0' },
  { key: 'PC', name: 'Photo Cyan', color: 'var(--ink-pc)', hex: '#73cdeb' },
  { key: 'M', name: 'Magenta', color: 'var(--ink-m)', hex: '#e2007a' },
  { key: 'PM', name: 'Photo Magenta', color: 'var(--ink-pm)', hex: '#f28dc0' },
  { key: 'Y', name: 'Yellow', color: 'var(--ink-y)', hex: '#ffdd00' },
  { key: 'R', name: 'Red', color: 'var(--ink-r)', hex: '#e4002b' },
  { key: 'CO', name: 'Chroma Optimizer', color: 'var(--ink-co)', hex: '#d9d9d9' },
]

const MARK_HEIGHTS = [0.62, 0.78, 0.52, 1, 0.84, 0.94, 0.7, 0.88, 0.6, 0.44]

export function InkMark({ size = 22 }: { size?: number }) {
  return (
    <span className="inkmark" aria-hidden="true" style={{ height: size }}>
      {INKS.map((ink, i) => (
        <i key={ink.key} style={{ height: `${MARK_HEIGHTS[i] * 100}%`, background: ink.key === 'PBK' || ink.key === 'MBK' ? 'var(--text)' : ink.color, opacity: ink.key === 'MBK' ? 0.55 : 1 }} />
      ))}
    </span>
  )
}

export function InkProgress() {
  return (
    <div className="progress-ink" aria-hidden="true">
      {INKS.map((ink, i) => (
        <i key={ink.key} style={{ background: ink.key.endsWith('BK') ? 'var(--text-2)' : ink.color, ['--i' as string]: i } as React.CSSProperties} />
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

const INK_BY_KEY = Object.fromEntries(INKS.map((i) => [i.key, i]))

/** Printmich's estimated tank levels (refilled or third-party ink). */
function EstimatedLevels({ tanks }: { tanks: InkTank[] }) {
  return (
    <div className="ink-row est" role="list" aria-label="Estimated ink levels">
      {tanks.map((t) => {
        const known = t.percent != null
        const lvl = known ? Math.max(0, Math.min(100, t.percent!)) : 0
        const title = known ? `${t.name}: about ${t.level_ml?.toFixed(1)} ml (${Math.round(lvl)}%), estimated` : `${t.name}: not tracked yet`
        return (
          <div className={`ink ${t.status}${t.ink.endsWith('BK') ? ' blk' : ''}`} key={t.ink} role="listitem" title={title}>
            <div className="tank">
              <div className={`fill${t.status === 'low' || t.status === 'empty' ? ' low' : ''}`} style={{ height: `${lvl}%`, background: INK_BY_KEY[t.ink]?.color ?? t.color }} />
            </div>
            <span className="lbl">{t.ink}</span>
          </div>
        )
      })}
    </div>
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

export function InkLevels({ markers, tanks }: { markers: Marker[]; tanks?: InkTank[] }) {
  if (tanks?.length) return <EstimatedLevels tanks={tanks} />
  if (!markers.length) return <div className="faint small">The printer doesn't report ink levels.</div>
  return (
    <div className="ink-row" role="list" aria-label="Ink levels">
      {markers.map((m) => {
        const level = m.level < 0 ? null : Math.max(0, Math.min(100, (m.level / (m.high || 100)) * 100))
        const low = level != null && m.level <= m.low
        const key = shortName(m.name)
        return (
          <div className={`ink${key === 'MBK' || key === 'PBK' ? ' blk' : ''}`} key={m.name} role="listitem" title={`${m.name}: ${level == null ? 'unknown' : `${Math.round(level)}%`}`}>
            <div className="tank">
              <div className={`fill${low ? ' low' : ''}`} style={{ height: `${level ?? 0}%`, background: m.color }} />
            </div>
            <span className="lbl">{shortName(m.name)}</span>
          </div>
        )
      })}
    </div>
  )
}

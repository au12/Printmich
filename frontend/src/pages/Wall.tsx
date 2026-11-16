import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, EyeOff, ExternalLink, Printer, X } from 'lucide-react'
import { api, immichLink, thumbUrl } from '../lib/api'
import { useInvalidate, usePresets, usePrints, useStats, useStatus } from '../lib/hooks'
import type { PrintItem } from '../lib/types'
import { camera, exposureParts, fmtDate, fmtDateTime, money, photoTitle, place, plural, takenDate } from '../lib/format'
import { Histogram } from '../components/Histogram'
import { PrintSheet } from '../components/PrintSheet'
import { Dialog, Field, Loading, Segmented, Select, Spinner, useToast } from '../components/ui'
import { InkMark } from '../components/Ink'

function useColumns(ref: React.RefObject<HTMLDivElement | null>) {
  const [cols, setCols] = useState(4)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => {
      const w = e.contentRect.width
      setCols(w < 520 ? 2 : w < 900 ? 3 : w < 1300 ? 4 : w < 1800 ? 5 : 6)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return cols
}

type Tile = { kind: 'intro' } | { kind: 'print'; item: PrintItem; index: number }

function Intro({ title, wide }: { title: string; wide?: boolean }) {
  const stats = useStats()
  const s = stats.data
  const since = s?.since ? new Date(s.since) : null
  const topPaper = s?.by_paper?.[0]
  return (
    <div className={`wall-intro${wide ? ' wide' : ''}`}>
      <div className="stack-s">
        <InkMark size={22} />
        <h1 className="h1" style={{ marginTop: 10 }}>{title}</h1>
        {since && <div className="small muted">Since {fmtDate(since, { month: 'long', year: 'numeric' })}</div>}
      </div>
      <div>
        <div className="big num">{(s?.total ?? 0).toLocaleString()}</div>
        <div className="small muted">photos printed</div>
      </div>
      <div className="stat-list">
        <div><b className="num">{s?.this_month ?? 0}</b>this month</div>
        <div><b className="num">{s?.streak ?? 0}</b>day streak</div>
        {topPaper && <div style={{ gridColumn: '1 / -1' }}><b>{topPaper.name}</b>most-used paper</div>}
        {s?.cost ? <div><b className="num">{money(s.cost)}</b>paper &amp; ink</div> : null}
        {s?.years?.length ? <div><b className="num">{s.years[0]}–{s.years[s.years.length - 1]}</b>photos from</div> : null}
      </div>
    </div>
  )
}

function ReprintDialog({ item, onClose }: { item: PrintItem; onClose: () => void }) {
  const presets = usePresets()
  const toast = useToast()
  const [presetId, setPresetId] = useState(item.preset_id ?? '')
  return (
    <Dialog title="Print again" onClose={onClose} footer={
      <>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-paper" onClick={async () => {
          try {
            await api.post(`/api/prints/${item.id}/reprint`, presetId && presetId !== item.preset_id ? { preset_id: presetId } : {})
            toast.ok('Sent to the print queue.')
            onClose()
          } catch (e) { toast.error(e) }
        }}><Printer /> Print</button>
      </>
    }>
      <Field label="Preset" hint="Uses the same crop as last time.">
        <Select value={presetId} onChange={setPresetId}
          options={[...(presets.data ?? []).map((p) => ({ value: p.id, label: p.name })),
            ...(item.preset_id && !presets.data?.some((p) => p.id === item.preset_id) ? [{ value: item.preset_id, label: `${item.preset_name} (as printed)` }] : [])]} />
      </Field>
    </Dialog>
  )
}

function Viewer({ items, index, onIndex, onClose, onHide }: { items: PrintItem[]; index: number; onIndex: (i: number) => void; onClose: () => void; onHide: (p: PrintItem) => void }) {
  const p = items[index]
  const [mode, setMode] = useState<'photo' | 'print'>('photo')
  const [reprint, setReprint] = useState(false)
  const status = useStatus()
  const stripRef = useRef<HTMLDivElement>(null)
  const touch = useRef<number | null>(null)

  const go = useCallback((d: number) => onIndex(Math.max(0, Math.min(items.length - 1, index + d))), [index, items.length, onIndex])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (reprint) return
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') go(1)
      if (e.key === 'ArrowLeft') go(-1)
    }
    window.addEventListener('keydown', h)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', h); document.body.style.overflow = '' }
  }, [go, onClose, reprint])
  useEffect(() => {
    stripRef.current?.querySelector('.on')?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [index])

  if (!p) return null
  const a = p.asset
  const big = p.asset_id ? thumbUrl(p.asset_id, 'preview') : p.thumb
  const g = p.geometry as { layout_mm?: [number, number] } | null
  const pageAspect = g?.layout_mm ? g.layout_mm[0] / g.layout_mm[1] : 2 / 3
  const exp = a ? exposureParts(a) : []

  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label={photoTitle(a)}
      onTouchStart={(e) => { touch.current = e.touches[0].clientX }}
      onTouchEnd={(e) => { if (touch.current != null) { const dx = e.changedTouches[0].clientX - touch.current; if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1); touch.current = null } }}>
      {p.thumb && <div className="viewer-ambient" style={{ backgroundImage: `url(${p.thumb})` }} />}
      <button className="btn btn-icon viewer-close" onClick={onClose} aria-label="Close"><X /></button>
      <div className="viewer-stage">
        {index > 0 && <button className="btn btn-icon viewer-nav" style={{ left: 14 }} onClick={() => go(-1)} aria-label="Previous"><ChevronLeft /></button>}
        {index < items.length - 1 && <button className="btn btn-icon viewer-nav" style={{ right: 14 }} onClick={() => go(1)} aria-label="Next"><ChevronRight /></button>}
        {mode === 'photo' ? (
          big ? <img key={p.id} src={big} alt={photoTitle(a)} /> : null
        ) : (
          <PrintSheet key={`${p.id}-page`} src={p.page} aspect={pageAspect} finish={p.paper.finish} tint={p.paper.tint} maxHeight="calc(100vh - 170px)" />
        )}
      </div>
      <div className="viewer-strip" ref={stripRef}>
        {items.map((it, i) => (
          <button key={it.id} className={i === index ? 'on' : ''} onClick={() => onIndex(i)} aria-label={photoTitle(it.asset)}>
            {it.thumb && <img src={it.thumb} alt="" loading="lazy" />}
          </button>
        ))}
      </div>
      <aside className="viewer-side">
        <div className="stack">
          <div>
            <h2 className="h2">{photoTitle(a)}</h2>
            <div className="small" style={{ color: '#9a9a9a', marginTop: 4 }}>
              {[a?.description ? place(a) : '', fmtDate(takenDate(a))].filter(Boolean).join(', ')}
            </div>
          </div>
          <Segmented value={mode} onChange={setMode} block ariaLabel="View"
            options={[{ value: 'photo', label: 'Photo' }, { value: 'print', label: 'As printed' }]} />
          <div className="btn-row">
            {p.asset_id && <button className="btn btn-paper btn-sm" onClick={() => setReprint(true)}><Printer /> Print again</button>}
            {p.asset_id && status.data?.immich && <a className="btn btn-sm" href={immichLink(p.asset_id)} target="_blank" rel="noreferrer"><ExternalLink /> Immich</a>}
            <button className="btn btn-sm btn-icon" title="Hide from the wall" aria-label="Hide from the wall" onClick={() => onHide(p)}><EyeOff /></button>
          </div>
          <hr className="divider" style={{ margin: '2px 0' }} />
          <div className="h3" style={{ color: '#f0f0f0' }}>Print</div>
          <dl className="kv">
            <dt>Printed</dt><dd>{fmtDateTime(p.completed_at || p.created_at)}</dd>
            <dt>Paper</dt><dd>{p.paper.name}{p.paper.code ? ` (${p.paper.code})` : ''}</dd>
            <dt>Size</dt><dd>{p.size_label}{p.borderless ? ', borderless' : ''}</dd>
            {p.preset_name && (<><dt>Preset</dt><dd>{p.preset_name}</dd></>)}
            {p.plan?.summary && (<><dt>Output</dt><dd>{p.plan.summary}</dd></>)}
            {p.effective_ppi ? (<><dt>Detail</dt><dd className="num">{Math.round(p.effective_ppi)} ppi</dd></>) : null}
            {p.copies > 1 && (<><dt>Copies</dt><dd>{p.copies}</dd></>)}
            {p.cost ? (<><dt>Cost</dt><dd>{money(p.cost)}</dd></>) : null}
            {p.source === 'schedule' && (<><dt>Chosen by</dt><dd>Schedule</dd></>)}
          </dl>
          {a && (
            <>
              <hr className="divider" style={{ margin: '2px 0' }} />
              <div className="h3" style={{ color: '#f0f0f0' }}>Photo</div>
              {p.thumb && <Histogram src={p.thumb} />}
              <dl className="kv">
                {camera(a) && (<><dt>Camera</dt><dd>{camera(a)}</dd></>)}
                {a.lens && (<><dt>Lens</dt><dd>{a.lens}</dd></>)}
                {exp.map((e) => (<div key={e.label} style={{ display: 'contents' }}><dt>{e.label}</dt><dd className="num">{e.value}</dd></div>))}
                {a.width && a.height && (<><dt>Original</dt><dd className="num">{a.width} × {a.height} px</dd></>)}
                {place(a) && (<><dt>Place</dt><dd>{place(a)}</dd></>)}
                {a.people.length > 0 && (<><dt>People</dt><dd>{a.people.join(', ')}</dd></>)}
                <dt>File</dt><dd>{a.filename}</dd>
              </dl>
            </>
          )}
        </div>
      </aside>
      {reprint && <ReprintDialog item={p} onClose={() => setReprint(false)} />}
    </div>
  )
}

export function WallPage() {
  const ref = useRef<HTMLDivElement>(null)
  const cols = useColumns(ref)
  const [params, setParams] = useSearchParams()
  const [year, setYear] = useState<string>('')
  const status = useStatus()
  const prints = usePrints({ status: 'completed', year: year || undefined })
  const invalidate = useInvalidate()
  const toast = useToast()
  const items = useMemo(() => prints.data?.pages.flatMap((p) => p.items) ?? [], [prints.data])
  const sentinel = useRef<HTMLDivElement>(null)
  const openId = params.get('print')
  const openIndex = openId ? items.findIndex((i) => i.id === openId) : -1

  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting && prints.hasNextPage && !prints.isFetchingNextPage) prints.fetchNextPage() }, { rootMargin: '800px' })
    io.observe(el)
    return () => io.disconnect()
  }, [prints])

  // On phones the intro would squeeze into one of two columns, so it sits above the wall instead.
  const introInline = cols > 2
  const columns = useMemo(() => {
    const out: Tile[][] = Array.from({ length: cols }, () => [])
    const heights = new Array(cols).fill(0)
    if (introInline) {
      out[0].push({ kind: 'intro' })
      heights[0] += 1.15
    }
    items.forEach((item, index) => {
      const ratio = item.thumb_w && item.thumb_h ? item.thumb_h / item.thumb_w : 0.75
      let c = 0
      for (let i = 1; i < cols; i++) if (heights[i] < heights[c] - 0.01) c = i
      out[c].push({ kind: 'print', item, index })
      heights[c] += ratio
    })
    return out
  }, [items, cols, introInline])

  const years = useMemo(() => {
    const now = new Date().getFullYear()
    return Array.from({ length: 6 }, (_, i) => String(now - i))
  }, [])

  const open = (id: string | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('print', id)
    else next.delete('print')
    setParams(next, { replace: !!openId && !!id })
  }

  return (
    <div className="wall" ref={ref}>
      <div className="wall-bar">
        <span className="small muted" style={{ whiteSpace: 'nowrap', paddingLeft: 4 }}>
          {prints.data ? plural(prints.data.pages[0]?.total ?? 0, 'print') : ''}{year ? ` from ${year}` : ''}
        </span>
        <Select value={year} onChange={setYear} ariaLabel="Year printed"
          options={[{ value: '', label: 'All years' }, ...years.map((y) => ({ value: y, label: `Printed in ${y}` }))]} />
      </div>
      {!introInline && !prints.isLoading && <Intro wide title={status.data?.wall_title || 'Printed moments'} />}
      {prints.isLoading ? <Loading label="Hanging prints" /> : (
        <div className="masonry">
          {columns.map((col, ci) => (
            <div className="masonry-col" key={ci}>
              {col.map((t) => t.kind === 'intro' ? <Intro key="intro" title={status.data?.wall_title || 'Printed moments'} /> : (
                <button key={t.item.id} className="tile" onClick={() => open(t.item.id)}
                  style={{ aspectRatio: t.item.thumb_w && t.item.thumb_h ? `${t.item.thumb_w} / ${t.item.thumb_h}` : '4 / 3' }}>
                  {t.item.thumb && <img src={t.item.thumb} alt={photoTitle(t.item.asset)} loading="lazy" decoding="async" />}
                  <span className="tile-info">
                    <strong className="ellipsis">{photoTitle(t.item.asset)}</strong>
                    <span>{t.item.size_label}, {t.item.paper.name}</span>
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
      {!prints.isLoading && items.length === 0 && (
        <div className="muted" style={{ padding: '10px 18px 40px' }}>Prints appear here as soon as they come out of the printer.</div>
      )}
      <div ref={sentinel} style={{ height: 1 }} />
      {prints.isFetchingNextPage && <div className="row" style={{ justifyContent: 'center', padding: 20 }}><Spinner /></div>}
      {openIndex >= 0 && (
        <Viewer items={items} index={openIndex} onIndex={(i) => open(items[i].id)} onClose={() => open(null)}
          onHide={async (p) => {
            try {
              await api.patch(`/api/prints/${p.id}`, { hidden: true })
              toast.ok('Hidden from the wall. It stays in your history.')
              open(null)
              invalidate('prints', 'stats')
            } catch (e) { toast.error(e) }
          }} />
      )}
    </div>
  )
}

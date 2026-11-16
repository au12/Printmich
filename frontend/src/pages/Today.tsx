import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarClock, Camera, Check, MapPin, Printer, Shuffle, SkipForward, Sparkles, X } from 'lucide-react'
import { api } from '../lib/api'
import { useDashboard, useInvalidate, usePapers, usePresets, useRenderPreview } from '../lib/hooks'
import type { Dashboard, DashboardSchedule, Pick, PrintItem } from '../lib/types'
import { ACTIVE_STATUSES, STATUS_TEXT, camera, fmtDate, photoTitle, place, plural, relativeTime, takenDate, whenLabel } from '../lib/format'
import { PrintSheet } from '../components/PrintSheet'
import { InkLevels, InkProgress } from '../components/Ink'
import { Empty, Loading, Spinner, useToast } from '../components/ui'

const SCORE_LABELS: Record<string, string> = {
  sharpness: 'Sharpness', exposure: 'Exposure', framing: 'Fits the paper', resolution: 'Resolution',
  favorite: 'Favorite', people: 'People', color: 'Color',
}

function Checklist({ items }: { items: Dashboard['checklist'] }) {
  if (items.every((i) => i.done)) return null
  const links: Record<string, string> = { immich: '/settings', printer: '/printer', preset: '/presets', schedule: '/schedules' }
  return (
    <section style={{ marginBottom: 30 }} aria-label="Setup steps">
      <div className="checklist">
        {items.map((i, n) => (
          <Link key={i.key} to={links[i.key]} className={`check-step${i.done ? ' done' : ''}`}>
            <span className="n">{i.done ? <Check size={13} /> : n + 1}</span>
            <span>
              <span style={{ fontWeight: 560 }}>{i.label}</span>
              <span className="small faint" style={{ display: 'block' }}>{i.done ? 'Done' : 'Set up'}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}

function WhyThis({ pick }: { pick: Pick }) {
  const c = pick.score?.components
  if (!c || !Object.keys(c).length) return null
  const keys = ['sharpness', 'exposure', 'framing', 'resolution', 'favorite'].filter((k) => k in c)
  return (
    <div>
      <div className="label" style={{ marginBottom: 8 }}>Why this photo</div>
      <div className="why">
        {keys.map((k) => (
          <div key={k} style={{ display: 'contents' }}>
            <span className="muted">{SCORE_LABELS[k]}</span>
            <span className="bar"><i style={{ width: `${Math.round((c[k] ?? 0) * 100)}%` }} /></span>
            <span className="num faint" style={{ textAlign: 'right' }}>{Math.round((c[k] ?? 0) * 100)}</span>
          </div>
        ))}
      </div>
      {pick.score.pool ? <div className="small faint" style={{ marginTop: 8 }}>Best of {pick.score.pool > 8 ? 8 : pick.score.pool} candidates from {plural(pick.score.pool, 'eligible photo')}.</div> : null}
    </div>
  )
}

function UpNext({ s, queue }: { s: DashboardSchedule; queue: PrintItem[] }) {
  const toast = useToast()
  const invalidate = useInvalidate()
  const papers = usePapers()
  const presets = usePresets()
  const [busy, setBusy] = useState<string | null>(null)
  const [ejectKey, setEjectKey] = useState(0)
  const pick = s.pick
  const preset = presets.data?.find((p) => p.id === s.preset_id)
  const paper = papers.data?.find((p) => p.id === preset?.output.paper_id)
  const preview = useRenderPreview(pick ? { asset_id: pick.asset_id, preset_id: s.preset_id, max_px: 1300 } : null, [], 0)
  const g = preview.info?.geometry
  const aspect = g ? g.layout_mm[0] / g.layout_mm[1] : 2 / 3
  const printing = queue.find((q) => q.schedule_id === s.id && ACTIVE_STATUSES.includes(q.status))

  async function act(name: string, fn: () => Promise<unknown>, done?: string) {
    setBusy(name)
    try {
      await fn()
      if (done) toast.ok(done)
      invalidate('dashboard', 'schedules', 'prints')
    } catch (e) {
      toast.error(e)
    } finally {
      setBusy(null)
    }
  }

  const a = pick?.asset
  const status = pick?.status
  return (
    <section className="today-hero" aria-label="Up next">
      <div className="table hero-table">
        <span className="slot" aria-hidden="true" />
        {pick ? (
          <div key={ejectKey} style={{ width: '100%', display: 'grid', placeItems: 'center', paddingTop: 10 }}>
            <PrintSheet src={preview.url} aspect={aspect} finish={paper?.finish} sheen={paper?.sheen} tint={paper?.tint}
              maxHeight="var(--hero-h)" eject={ejectKey > 0} alt={a ? photoTitle(a) : ''}>
              {!preview.url && <div className="sheet-loading"><Spinner /></div>}
            </PrintSheet>
          </div>
        ) : (
          <div className="stack" style={{ alignItems: 'center', textAlign: 'center', maxWidth: 340 }}>
            <div className="sheet" style={{ width: 180, aspectRatio: '2 / 3', background: 'transparent', boxShadow: 'none', border: '1.5px dashed var(--line-strong)' }} />
            <div className="muted small">
              {s.approval === 'auto'
                ? `A photo is chosen at print time.`
                : `A photo is chosen ${whenLabel(s.next_run_at) ? 'about 12 hours before printing' : 'before printing'}.`}
            </div>
            <button className="btn" disabled={!!busy} onClick={() => act('pick', () => api.post(`/api/schedules/${s.id}/pick`))}>
              {busy === 'pick' ? <Spinner size={14} /> : <Sparkles />} Choose a photo now
            </button>
          </div>
        )}
        {printing && (
          <div style={{ position: 'absolute', left: 24, right: 24, bottom: 18 }}>
            <div className="row-between small" style={{ marginBottom: 8 }}>
              <span>{STATUS_TEXT[printing.status]}</span><span className="faint">{printing.detail}</span>
            </div>
            <InkProgress />
          </div>
        )}
      </div>

      <div className="upnext-meta">
        <div className="row small muted" style={{ gap: 8 }}>
          <CalendarClock size={15} />
          <span><Link to="/schedules" style={{ textDecoration: 'none', fontWeight: 560, color: 'var(--text)' }}>{s.name}</Link>{' '}
            {status === 'skipped' ? 'is skipping its next print' : `prints ${whenLabel(s.next_run_at).replace(/^./, (c) => c.toLowerCase())}`}</span>
        </div>
        {a ? (
          <>
            <h2 className="upnext-title">{photoTitle(a)}</h2>
            <div className="facts">
              {takenDate(a) && <span><CalendarClock /> {fmtDate(takenDate(a))}</span>}
              {place(a) && a.description && <span><MapPin /> {place(a)}</span>}
              {camera(a) && <span><Camera /> {camera(a)}</span>}
            </div>
            <div className="small muted">
              From <span style={{ color: 'var(--text)' }}>{pick?.source}</span>, printed as{' '}
              <span style={{ color: 'var(--text)' }}>{s.preset_name}</span>
              {preview.info && <span className="faint"> on {preview.info.plan.media_type_label.toLowerCase()} via the {preview.info.plan.media_source_label.toLowerCase()}</span>}.
            </div>
            {status === 'skipped' ? (
              <div className="btn-row">
                <button className="btn btn-paper" disabled={!!busy} onClick={() => act('unskip', () => api.post(`/api/picks/${pick!.id}/unskip`), 'Back on the schedule.')}>
                  <Check /> Print it after all
                </button>
                <button className="btn" disabled={!!busy} onClick={() => act('pick', () => api.post(`/api/schedules/${s.id}/pick`))}><Shuffle /> Pick another</button>
              </div>
            ) : (
              <div className="btn-row">
                {s.approval === 'manual' && status === 'pending' && (
                  <button className="btn btn-paper" disabled={!!busy} onClick={() => act('approve', () => api.post(`/api/picks/${pick!.id}/approve`), `Approved — it prints ${whenLabel(s.next_run_at).toLowerCase()}.`)}>
                    <Check /> Approve
                  </button>
                )}
                <button className={`btn ${s.approval === 'manual' && status === 'pending' ? '' : 'btn-paper'}`} disabled={!!busy || !!printing}
                  onClick={() => act('print', async () => { await api.post(`/api/schedules/${s.id}/run`); setEjectKey((k) => k + 1) }, 'Printing now.')}>
                  {busy === 'print' ? <Spinner size={14} /> : <Printer />} Print now
                </button>
                <button className="btn" disabled={!!busy} onClick={() => act('pick', () => api.post(`/api/schedules/${s.id}/pick`))}>
                  {busy === 'pick' ? <Spinner size={14} /> : <Shuffle />} Pick another
                </button>
                <button className="btn btn-ghost" disabled={!!busy} onClick={() => act('skip', () => api.post(`/api/schedules/${s.id}/skip`), 'Skipped. The next one is still on.')}>
                  <SkipForward /> Skip
                </button>
              </div>
            )}
            {pick && <WhyThis pick={pick} />}
          </>
        ) : (
          <>
            <h2 className="upnext-title">{s.timing_text}</h2>
            <p className="muted" style={{ margin: 0 }}>Next print {whenLabel(s.next_run_at).toLowerCase()}, using <strong style={{ color: 'var(--text)' }}>{s.preset_name}</strong>.</p>
          </>
        )}
      </div>
    </section>
  )
}

function PrinterStrip({ d }: { d: Dashboard }) {
  const p = d.printer
  if (!p.configured) {
    return <Empty title="Connect your printer" action={<Link className="btn btn-paper" to="/printer"><Printer /> Set up printer</Link>}>
      Printmich talks to the PRO-310 directly over the network (IPP Everywhere), so no driver is needed.
    </Empty>
  }
  const loaded = p.ready?.[0]
  const cls = !p.online ? 'err' : d.queue.length ? 'busy' : p.state === 'stopped' ? 'warn' : 'ok'
  const text = !p.online ? 'Offline' : d.queue.length ? 'Printing' : p.state === 'stopped' ? 'Needs attention' : 'Ready'
  return (
    <div className="panel printer-strip">
      <div className="stack-s">
        <div className="row"><span className={`dot ${cls}`} /><span className="h3">{text}</span></div>
        {p.online && loaded?.size_label && (
          <div className="small muted">Loaded: <span style={{ color: 'var(--text)' }}>{loaded.size_label}{loaded.type_label ? `, ${loaded.type_label.toLowerCase()}` : ''}</span>{loaded.source_label ? ` in the ${loaded.source_label.toLowerCase()}` : ''}</div>
        )}
        {(p.reasons ?? []).map((r) => <div key={r.keyword} className="small" style={{ color: r.severity === 'error' ? 'var(--err)' : 'var(--warn)' }}>{r.text}</div>)}
        {!p.online && <div className="small muted">{p.error}</div>}
        <Link to="/printer" className="small faint">Printer details</Link>
      </div>
      <InkLevels markers={p.markers ?? []} />
    </div>
  )
}

function QueueList({ queue }: { queue: PrintItem[] }) {
  const toast = useToast()
  const invalidate = useInvalidate()
  if (!queue.length) return null
  return (
    <section className="section">
      <div className="section-head"><h2 className="h2">In progress</h2></div>
      <div className="panel panel-tight">
        <div className="list">
          {queue.map((q) => (
            <div key={q.id} className="list-row">
              <span className={`dot ${q.status === 'held' || q.status === 'waiting' ? 'warn' : 'busy'}`} />
              <div className="grow">
                <div className="ellipsis" style={{ fontWeight: 560 }}>{photoTitle(q.asset)}</div>
                <div className="small muted ellipsis">{STATUS_TEXT[q.status]}: {q.detail}</div>
              </div>
              {q.status === 'held' && (
                <button className="btn btn-sm" onClick={async () => { await api.post(`/api/prints/${q.id}/release`); invalidate('dashboard') }}>Print anyway</button>
              )}
              <button className="btn btn-ghost btn-sm" onClick={async () => {
                try { await api.post(`/api/prints/${q.id}/cancel`); toast.ok('Canceled.'); invalidate('dashboard') } catch (e) { toast.error(e) }
              }}><X /> Cancel</button>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Recent({ items }: { items: PrintItem[] }) {
  const navigate = useNavigate()
  const done = items.filter((p) => p.status === 'completed' || p.status === 'failed')
  if (!done.length) return null
  return (
    <section className="section">
      <div className="section-head">
        <h2 className="h2">Recently printed</h2>
        <Link to="/wall" className="small muted">See the wall</Link>
      </div>
      <div className="strip">
        {done.map((p) => {
          const g = p.geometry as { layout_mm?: [number, number] } | null
          const aspect = g?.layout_mm ? g.layout_mm[0] / g.layout_mm[1] : 2 / 3
          return (
            <button key={p.id} className="mini-print" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left', width: aspect >= 1 ? 190 : 120 }}
              onClick={() => navigate(`/wall?print=${p.id}`)}>
              <div style={{ height: 150, display: 'flex', alignItems: 'flex-end' }}>
                <PrintSheet src={p.page} aspect={aspect} finish={p.paper.finish} tint={p.paper.tint} />
              </div>
              <div className="cap">
                <div className="ellipsis" style={{ color: 'var(--text)' }}>{photoTitle(p.asset)}</div>
                <div className="faint">{p.status === 'failed' ? 'Failed' : relativeTime(p.completed_at || p.created_at)}</div>
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function Activity({ events }: { events: Dashboard['events'] }) {
  if (!events.length) return null
  return (
    <section className="section">
      <div className="section-head"><h2 className="h2">Activity</h2></div>
      <div className="activity">
        {events.slice(0, 10).map((e) => (
          <div key={e.id} className="activity-item">
            <span className={`dot ${e.level === 'error' ? 'err' : e.level === 'warning' ? 'warn' : e.level === 'success' ? 'ok' : ''}`} />
            <span>{e.message}</span>
            <span className="small faint num">{relativeTime(e.ts)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export function TodayPage() {
  const { data, isLoading, error } = useDashboard()
  if (isLoading) return <Loading />
  if (error || !data) return <div className="page"><Empty title="Printmich isn't responding">{(error as Error)?.message}</Empty></div>
  const today = new Date()
  const s = data.stats
  const up = data.upcoming
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h-display">{today.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</h1>
          <p className="lede">
            {s.total ? `${plural(s.this_month, 'print')} this month, ${plural(s.total, 'print')} in all.` : 'Nothing printed yet.'}{' '}
            {up ? `The next one prints ${whenLabel(up.next_run_at).replace(/^./, (c) => c.toLowerCase())}.` : 'No schedule is turned on.'}
          </p>
        </div>
        <div className="actions">
          <Link to="/library" className="btn"><Printer /> Print a photo</Link>
        </div>
      </header>

      <Checklist items={data.checklist} />

      {up ? <UpNext s={up} queue={data.queue} /> : (
        <Empty title="Turn on a schedule to get a photo of the day"
          action={<Link to="/schedules" className="btn btn-paper"><CalendarClock /> Open schedules</Link>}>
          Pick when to print and where photos come from: favorites, albums, people, or the photos you took on this day in past years.
        </Empty>
      )}

      <QueueList queue={data.queue} />

      <section className="section">
        <div className="section-head"><h2 className="h2">Printer</h2></div>
        <PrinterStrip d={data} />
      </section>

      <Recent items={data.recent} />
      <Activity events={data.events} />
    </div>
  )
}

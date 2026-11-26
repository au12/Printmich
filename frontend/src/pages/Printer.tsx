import { useEffect, useState } from 'react'
import { Bell, CircleHelp, Download, ExternalLink, FlaskConical, RefreshCw, Search, Wifi, X } from 'lucide-react'
import { api } from '../lib/api'
import { useInvalidate, usePrinter, useSettings } from '../lib/hooks'
import type { PrinterInfo } from '../lib/types'
import { round } from '../lib/format'
import { InkLevels } from '../components/Ink'
import { InkPanel } from '../components/InkPanel'
import { Empty, Field, Loading, Notice, Spinner, useToast } from '../components/ui'

type Found = { name: string; uri: string; model: string; host: string; secure: boolean }

function Connect({ current, locked, onDone }: { current?: string; locked: boolean; onDone: () => void }) {
  const toast = useToast()
  const [address, setAddress] = useState(current && !current.startsWith('virtual') ? current : '')
  const [found, setFound] = useState<Found[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function save(uri: string, name = '') {
    setBusy('save')
    try {
      await api.put('/api/printer', { uri, name })
      toast.ok(uri.startsWith('virtual') ? 'Using the virtual printer.' : 'Printer connected.')
      onDone()
    } catch (e) { toast.error(e) } finally { setBusy(null) }
  }

  if (locked) return <Notice>The printer address is set by the <strong>PRINTER_URI</strong> environment variable.</Notice>
  return (
    <div className="stack">
      <form className="row wrap" style={{ alignItems: 'flex-end' }} onSubmit={async (e) => {
        e.preventDefault()
        setBusy('probe')
        try {
          const r = await api.post<{ uri: string; model: string }>('/api/printer/probe', { address })
          await save(r.uri, r.model)
        } catch (err) { toast.error(err) } finally { setBusy(null) }
      }}>
        <Field label="Printer address" hint="An IP address like 10.0.10.42 works; Printmich finds the right IPP path.">
          <input className="input" style={{ minWidth: 280 }} placeholder="10.0.10.42 or ipp://printer.local/ipp/print" value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <button className="btn btn-paper" disabled={!address || !!busy}>{busy === 'probe' ? <Spinner size={14} /> : <Wifi />} Connect</button>
        <button type="button" className="btn" disabled={!!busy} onClick={async () => {
          setBusy('discover')
          try { setFound(await api.get<Found[]>('/api/printer/discover')) } catch (e) { toast.error(e) } finally { setBusy(null) }
        }}>{busy === 'discover' ? <Spinner size={14} /> : <Search />} Find on network</button>
      </form>
      {found && (found.length ? (
        <div className="list panel panel-tight">
          {found.map((f) => (
            <div key={f.uri} className="list-row">
              <div className="grow"><div className="strong">{f.name}</div><div className="small faint">{f.model} at {f.host}{f.secure ? ', encrypted' : ''}</div></div>
              <button className="btn btn-sm btn-paper" onClick={() => save(f.uri, f.name)}>Use this printer</button>
            </div>
          ))}
        </div>
      ) : <div className="small muted">No printers answered. Network discovery needs the container on your LAN (host or br0 network on Unraid). Typing the IP address always works.</div>)}
      <div className="small faint">No printer handy? <button className="btn btn-ghost btn-sm" onClick={() => save('virtual://pro-310')}><FlaskConical /> Use the virtual printer</button> It renders every job exactly like a real one and saves it as an image.</div>
    </div>
  )
}

function Capabilities({ info }: { info: PrinterInfo }) {
  const c = info.capabilities!
  return (
    <div className="grid-2" style={{ alignItems: 'start' }}>
      <div className="panel">
        <div className="panel-head"><h3 className="h3">Paper sizes</h3><span className="small faint">{c.sizes.length}</span></div>
        <table className="table-list">
          <thead><tr><th>Size</th><th>mm</th><th>Borderless</th></tr></thead>
          <tbody>
            {c.sizes.map((s) => (
              <tr key={s.keyword}><td>{s.label}</td><td className="num faint">{round(s.width_mm)} × {round(s.height_mm)}</td><td>{s.borderless ? 'Yes' : ''}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="stack">
        <div className="panel">
          <h3 className="h3" style={{ marginBottom: 10 }}>Paper types</h3>
          <div className="row wrap" style={{ gap: 6 }}>{c.types.map((t) => <span key={t.keyword} className="chip" title={t.keyword}>{t.label}</span>)}</div>
          <h3 className="h3" style={{ margin: '18px 0 10px' }}>Feeds</h3>
          <div className="row wrap" style={{ gap: 6 }}>{c.sources.map((t) => <span key={t.keyword} className="chip" title={t.keyword}>{t.label}</span>)}</div>
        </div>
        <div className="panel">
          <dl className="kv">
            <dt>Documents</dt><dd>{c.formats.filter((f) => f !== 'application/octet-stream').join(', ')}</dd>
            <dt>Raster resolutions</dt><dd>{c.pwg_resolutions.map((r) => `${r} dpi`).join(', ') || 'None'}</dd>
            <dt>Raster color</dt><dd>{c.pwg_types.join(', ') || 'None'}</dd>
            <dt>Quality modes</dt><dd>{c.qualities.join(', ')}</dd>
            <dt>Color modes</dt><dd>{c.color_modes.join(', ')}</dd>
            <dt>Rendering intents</dt><dd>{c.rendering_intents.join(', ') || 'Not supported'}</dd>
            <dt>Minimum margins</dt><dd className="num">{c.hw_margins.top} / {c.hw_margins.right} / {c.hw_margins.bottom} / {c.hw_margins.left} mm</dd>
            <dt>Borderless</dt><dd>{c.borderless_capable ? 'Supported' : 'No'}</dd>
            <dt>Copies</dt><dd>Up to {c.copies_max}</dd>
          </dl>
        </div>
      </div>
    </div>
  )
}

function VirtualOutputs() {
  const [items, setItems] = useState<{ job_id: number; name: string; image: string | null; format: string }[]>([])
  useEffect(() => { api.get<typeof items>('/api/printer/virtual/outputs').then(setItems).catch(() => {}) }, [])
  if (!items.length) return null
  return (
    <section className="section">
      <div className="section-head"><h2 className="h2">Virtual printer output</h2><span className="small faint">Saved in /config/virtual-printer</span></div>
      <div className="strip">
        {items.slice(0, 20).map((i) => i.image && (
          <a key={i.job_id} href={`/api/printer/virtual/outputs/${i.image}`} target="_blank" rel="noreferrer" className="mini-print">
            <img src={`/api/printer/virtual/outputs/${i.image}`} alt="" style={{ height: 150, width: 'auto', boxShadow: 'var(--shadow-print)' }} />
            <span className="cap">Job {i.job_id}, {i.format.replace('image/', '')}</span>
          </a>
        ))}
      </div>
    </section>
  )
}

export function PrinterPage() {
  const printer = usePrinter()
  const settings = useSettings()
  const invalidate = useInvalidate()
  const toast = useToast()
  const [changing, setChanging] = useState(false)
  const [jobs, setJobs] = useState<{ active: { id: number; name: string; state: string; user: string }[] } | null>(null)
  const info = printer.data
  const locked = settings.data?.env_locked.includes('printer_uri') ?? false

  useEffect(() => {
    if (info?.configured && info.status?.online) api.get<typeof jobs>('/api/printer/jobs').then(setJobs).catch(() => setJobs(null))
  }, [info?.configured, info?.status?.online])

  if (printer.isLoading) return <Loading />
  const c = info?.capabilities
  const st = info?.status
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">{c ? (c.virtual ? 'Virtual PRO-310' : c.make_model || 'Printer') : 'Printer'}</h1>
          <p className="lede">{info?.configured ? <>Connected at <span className="num">{info.uri}</span> over IPP, with no driver involved.</> : 'Connect your Canon imagePROGRAF PRO-310 (or any AirPrint / IPP Everywhere printer).'}</p>
        </div>
        {info?.configured && (
          <div className="actions">
            <button className="btn" onClick={async () => { await api.post('/api/printer/refresh'); invalidate('printer', 'papers', 'sizes'); toast.ok('Refreshed.') }}><RefreshCw /> Refresh</button>
            <button className="btn" onClick={async () => { try { await api.post('/api/printer/identify'); toast.ok('Asked the printer to identify itself.') } catch (e) { toast.error(e) } }}><Bell /> Identify</button>
            <a className="btn" href="/api/printer/attributes" download><Download /> Attributes</a>
            {c?.admin_url && <a className="btn" href={c.admin_url} target="_blank" rel="noreferrer"><ExternalLink /> Printer web page</a>}
          </div>
        )}
      </header>

      {(!info?.configured || changing) ? (
        <div className="panel"><Connect current={info?.uri} locked={locked} onDone={() => { setChanging(false); invalidate('printer', 'dashboard', 'papers', 'sizes', 'status') }} /></div>
      ) : (
        <>
          {info.error && <Notice kind="err"><strong>Can't reach the printer.</strong> {info.error}</Notice>}
          {st && (
            <div className="panel printer-strip" style={{ alignItems: 'start' }}>
              <div className="stack">
                <div className="row"><span className={`dot ${!st.online ? 'err' : st.state === 'processing' ? 'busy' : st.state === 'stopped' ? 'warn' : 'ok'}`} />
                  <span className="h2">{!st.online ? 'Offline' : st.state === 'processing' ? 'Printing' : st.state === 'stopped' ? 'Needs attention' : 'Ready'}</span></div>
                {(st.reasons ?? []).map((r) => (
                  <div key={r.keyword} className="small" style={{ color: r.severity === 'error' ? 'var(--err)' : 'var(--warn)' }}>
                    {r.text}{r.hint && <span style={{ display: 'block', color: 'var(--text-2)' }}>{r.hint}</span>}
                  </div>
                ))}
                {st.ready?.length ? (
                  <dl className="kv">
                    {st.ready.map((r, i) => (
                      <div key={i} style={{ display: 'contents' }}>
                        <dt>{r.source_label ?? 'Loaded'}</dt><dd>{r.size_label ?? 'Unknown size'}{r.type_label ? `, ${r.type_label}` : ''}</dd>
                      </div>
                    ))}
                  </dl>
                ) : <div className="small faint">The printer doesn't report loaded paper.</div>}
                {!locked && <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setChanging(true)}>Change printer</button>}
              </div>
              <div className="stack">
                <div className="label">{st.ink?.tracking ? 'Ink, estimated' : 'Ink'}</div>
                <InkLevels markers={st.markers ?? []} tanks={st.ink?.tracking ? st.ink.tanks : undefined} />
              </div>
            </div>
          )}
          <InkPanel />
          {jobs?.active?.length ? (
            <section className="section">
              <div className="section-head"><h2 className="h2">Jobs at the printer</h2></div>
              <div className="panel panel-tight list">
                {jobs.active.map((j) => (
                  <div key={j.id} className="list-row"><span className="dot busy" /><span className="grow">{j.name || `Job ${j.id}`}</span><span className="small faint">{j.state}</span>
                    <button className="btn btn-ghost btn-sm" onClick={async () => { await api.post(`/api/printer/jobs/${j.id}/cancel`); toast.ok('Canceled at the printer.') }}><X /></button></div>
                ))}
              </div>
            </section>
          ) : null}
          {c && (
            <section className="section">
              <div className="section-head"><h2 className="h2">What it supports</h2><span className="small faint">{c.firmware && `Firmware ${c.firmware}`}</span></div>
              <Capabilities info={info} />
            </section>
          )}
          {c?.virtual && <VirtualOutputs />}
        </>
      )}
      {!info?.configured && !changing && <div style={{ marginTop: 18 }}><Empty icon={<CircleHelp />} title="Why no driver?">The PRO-310 speaks IPP Everywhere (the standard behind AirPrint and Mopria). Printmich renders each page itself and sends exact pixels, so color, sharpening and layout are fully under your control.</Empty></div>}
    </div>
  )
}

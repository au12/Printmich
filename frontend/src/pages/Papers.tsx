import { useEffect, useMemo, useState } from 'react'
import { FileImage, Grid3x3, Plus, Printer, RotateCcw, Trash2, Upload } from 'lucide-react'
import { api, postImage, thumbUrl } from '../lib/api'
import { useBrowse, useInvalidate, usePapers, usePresets, usePrinter, useSettings, useSizes } from '../lib/hooks'
import type { Adjustments, Paper, RenderInfo } from '../lib/types'
import { fmtDate, parseDate } from '../lib/format'
import { Confirm, Dialog, Drawer, Empty, Field, Loading, NumberInput, Segmented, Select, Slider, Spinner, Toggle, useToast } from '../components/ui'

const FINISH_LABEL: Record<string, string> = {
  'high-gloss': 'High gloss', glossy: 'Glossy', luster: 'Luster', 'semi-gloss': 'Semi-gloss', baryta: 'Baryta', matte: 'Matte',
  'premium-matte': 'Premium matte', 'fine-art-smooth': 'Fine art, smooth', 'fine-art-rough': 'Fine art, textured', canvas: 'Canvas', washi: 'Washi', plain: 'Plain',
}

const ADJ: { key: keyof Adjustments; label: string }[] = [
  { key: 'brightness', label: 'Brightness' }, { key: 'contrast', label: 'Contrast' }, { key: 'saturation', label: 'Intensity' },
  { key: 'shadows', label: 'Shadows' }, { key: 'highlights', label: 'Highlights' }, { key: 'cyan', label: 'Cyan' },
  { key: 'magenta', label: 'Magenta' }, { key: 'yellow', label: 'Yellow' },
]

export function PaperSwatch({ paper, height = 92 }: { paper: Paper; height?: number }) {
  const gloss = paper.sheen
  return (
    <div className="paper-swatch" style={{
      height,
      background: `linear-gradient(115deg, rgba(255,255,255,0) 30%, rgba(255,255,255,${0.75 * gloss}) 45%, rgba(255,255,255,0) 60%), ${paper.tint}`,
      filter: gloss < 0.1 ? 'contrast(0.97)' : undefined,
    }}>
      <span className="code">{paper.code || paper.brand}</span>
      <span className="label">{paper.name}</span>
    </div>
  )
}

function PatternTool({ paper, onApply }: { paper: Paper; onApply: (a: Adjustments) => void }) {
  const presets = usePresets()
  const favs = useBrowse('favorites')
  const toast = useToast()
  const samples = useMemo(() => favs.data?.pages[0]?.items.slice(0, 12) ?? [], [favs.data])
  const [assetId, setAssetId] = useState<string | null>(null)
  const [mode, setMode] = useState<'color' | 'tone'>('color')
  const [step, setStep] = useState(10)
  const [presetId, setPresetId] = useState('')
  const [img, setImg] = useState<{ url: string; info: RenderInfo } | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => { if (!assetId && samples.length) setAssetId(samples[0].id) }, [samples, assetId])
  useEffect(() => {
    if (!presetId && presets.data?.length) setPresetId((presets.data.find((p) => p.output.paper_id === paper.id) ?? presets.data[0]).id)
  }, [presets.data, presetId, paper.id])
  const body = { kind: 'pattern', preset_id: presetId, paper_id: paper.id, asset_id: assetId, mode, step, max_px: 1200, base: paper.calibration.adjust }
  useEffect(() => {
    if (!assetId || !presetId) return
    setLoading(true)
    const ctrl = new AbortController()
    postImage('/api/tools/preview', body, ctrl.signal).then(setImg).catch(() => {}).finally(() => setLoading(false))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId, presetId, mode, step, paper.calibration])
  return (
    <div className="stack">
      <div className="hint">Prints nine versions of one photo. Pick the one that best matches your screen and apply it to this paper.</div>
      <div className="row wrap" style={{ gap: 6 }}>
        {samples.map((s) => (
          <button key={s.id} onClick={() => setAssetId(s.id)} style={{ width: 40, height: 40, padding: 0, borderRadius: 4, overflow: 'hidden', border: s.id === assetId ? '2px solid var(--text)' : '2px solid transparent', cursor: 'pointer' }}>
            <img src={thumbUrl(s.id)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </button>
        ))}
      </div>
      <div className="grid-2">
        <Segmented value={mode} onChange={setMode} block options={[{ value: 'color', label: 'Color balance' }, { value: 'tone', label: 'Brightness & contrast' }]} />
        <Segmented value={step} onChange={setStep} block options={[5, 10, 15].map((v) => ({ value: v, label: `Step ${v}` }))} />
      </div>
      <Field label="Print on"><Select value={presetId} onChange={setPresetId} options={(presets.data ?? []).map((p) => ({ value: p.id, label: p.name }))} /></Field>
      <div style={{ position: 'relative', background: 'var(--g0)', borderRadius: 'var(--r-m)', padding: 12, minHeight: 200, display: 'grid', placeItems: 'center' }}>
        {img && <img src={img.url} alt="Color pattern preview" style={{ maxHeight: 360, boxShadow: 'var(--shadow-print)' }} />}
        {loading && <span style={{ position: 'absolute', top: 10, right: 10 }}><Spinner size={14} /></span>}
      </div>
      {img?.info.tiles && (
        <div className="grid-3">
          {img.info.tiles.map((t) => (
            <button key={t.index} className="btn btn-sm" onClick={() => { onApply(t.adjust); toast.ok(`Applied “${t.label}” to ${paper.name}. Save to keep it.`) }}
              disabled={t.label === 'Current'}>{t.index}. {t.label.split('  ')[0]}</button>
          ))}
        </div>
      )}
      <button className="btn btn-paper" disabled={!assetId || !presetId} onClick={async () => {
        try { await api.post('/api/tools/pattern', body); toast.ok('Pattern sent to the printer.') } catch (e) { toast.error(e) }
      }}><Grid3x3 /> Print pattern</button>
    </div>
  )
}

function PaperEditor({ initial, onClose }: { initial: Paper; onClose: () => void }) {
  const [p, setP] = useState<Paper>(structuredClone(initial))
  const printer = usePrinter()
  const presets = usePresets()
  const sizes = useSizes()
  const settings = useSettings()
  const toast = useToast()
  const invalidate = useInvalidate()
  const [chartPreset, setChartPreset] = useState('')
  const [confirm, setConfirm] = useState<'reset' | 'delete' | null>(null)
  const caps = printer.data?.capabilities
  const set = (fn: (x: Paper) => void) => setP((cur) => { const n = structuredClone(cur); fn(n); return n })
  useEffect(() => {
    if (!chartPreset && presets.data?.length) setChartPreset((presets.data.find((x) => x.output.paper_id === p.id) ?? presets.data[0]).id)
  }, [presets.data, chartPreset, p.id])

  async function save() {
    try {
      await api.put(`/api/papers/${p.id}`, p as unknown as Record<string, unknown>)
      toast.ok(`Saved ${p.name}.`)
      invalidate('papers')
      onClose()
    } catch (e) { toast.error(e) }
  }

  const currency = settings.data?.cost.currency ?? '$'
  const costSizes = Array.from(new Set([...p.sizes, ...Object.keys(p.cost_per_sheet)]))
  return (
    <Drawer title={p.name} onClose={onClose} footer={
      <>
        <div className="btn-row">
          {p.builtin && p.customized && <button className="btn btn-ghost" onClick={() => setConfirm('reset')}><RotateCcw /> Reset to defaults</button>}
          {!p.builtin && <button className="btn btn-ghost btn-danger" onClick={() => setConfirm('delete')}><Trash2 /> Delete</button>}
        </div>
        <div className="btn-row"><button className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-paper" onClick={save}>Save paper</button></div>
      </>
    }>
      <div className="stack" style={{ gap: 26 }}>
        <PaperSwatch paper={p} height={110} />
        <div className="prose small">{p.notes}</div>
        <dl className="kv">
          <dt>Finish</dt><dd>{FINISH_LABEL[p.finish] ?? p.finish}</dd>
          <dt>Black ink</dt><dd>{p.black_ink === 'matte' ? 'Matte Black (MBK)' : 'Photo Black (PBK)'}</dd>
          <dt>Feeds</dt><dd>{p.feeds.map((f) => (f === 'manual' ? 'Manual feed' : 'Top feed')).join(', ')}</dd>
          <dt>Borderless</dt><dd>{p.borderless ? 'Supported' : 'No'}</dd>
          {p.recommended_margins && (<><dt>Recommended margins</dt><dd>{p.recommended_margins.top} mm top and bottom</dd></>)}
        </dl>

        <section className="stack">
          <h3 className="h3">On your printer</h3>
          <Field label="Printer paper type" hint={p.resolved?.media_type ? `Automatic picks “${p.resolved.media_type.label}” (${p.resolved.media_type.how === 'hint' ? 'name match' : p.resolved.media_type.how === 'generic' ? 'closest standard type' : p.resolved.media_type.how}).` : 'Connect a printer to see its paper types.'}>
            <Select value={p.media_type} onChange={(v) => set((x) => { x.media_type = v })}
              options={[{ value: 'auto', label: 'Automatic' }, ...(caps?.types ?? []).map((t) => ({ value: t.keyword, label: `${t.label} (${t.keyword})` }))]} />
          </Field>
          <Field label="Default feed">
            <Segmented value={p.default_feed} onChange={(v) => set((x) => { x.default_feed = v })}
              options={[{ value: 'top', label: 'Top feed' }, { value: 'manual', label: 'Manual feed' }]} />
          </Field>
        </section>

        <section className="stack">
          <div className="row-between">
            <h3 className="h3">Calibration</h3>
            <span className="small faint">{p.calibration.calibrated_at ? `Calibrated ${fmtDate(parseDate(p.calibration.calibrated_at))}` : 'Starting values'}</span>
          </div>
          <div className="grid-2">
            <Field label="Rendering intent">
              <Select value={p.calibration.intent} onChange={(v) => set((x) => { x.calibration.intent = v })}
                options={[{ value: 'perceptual', label: 'Perceptual' }, { value: 'relative', label: 'Relative colorimetric' }, { value: 'saturation', label: 'Saturation' }, { value: 'absolute', label: 'Absolute colorimetric' }]} />
            </Field>
            <Field label="Output sharpening">
              <Select value={p.calibration.sharpening} onChange={(v) => set((x) => { x.calibration.sharpening = v })}
                options={[{ value: 'off', label: 'Off' }, { value: 'low', label: 'Low' }, { value: 'standard', label: 'Standard' }, { value: 'high', label: 'High' }]} />
            </Field>
          </div>
          <Toggle checked={p.calibration.bpc} onChange={(v) => set((x) => { x.calibration.bpc = v })} label="Black point compensation" />
          {ADJ.map((a) => (
            <Slider key={a.key} label={a.label} value={p.calibration.adjust[a.key]} min={-50} max={50}
              onChange={(v) => set((x) => { x.calibration.adjust[a.key] = v })} />
          ))}
          <Field label="Notes"><textarea className="textarea" value={p.calibration.notes} onChange={(e) => set((x) => { x.calibration.notes = e.target.value })} placeholder="What you changed and why" /></Field>
          <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => set((x) => { x.calibration.calibrated_at = new Date().toISOString() })}>Mark as calibrated today</button>
        </section>

        <section className="stack">
          <h3 className="h3">Calibration chart</h3>
          <div className="hint">A gray wedge, reference colors, shadow and highlight steps, gradients and fine lines, printed through this paper's calibration.</div>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <Field label="Print on"><Select value={chartPreset} onChange={setChartPreset} options={(presets.data ?? []).map((x) => ({ value: x.id, label: x.name }))} /></Field>
            <button className="btn" onClick={async () => {
              try { await api.post('/api/tools/chart', { preset_id: chartPreset, paper_id: p.id }); toast.ok('Calibration chart sent to the printer.') } catch (e) { toast.error(e) }
            }}><Printer /> Print chart</button>
          </div>
        </section>

        <section className="stack">
          <h3 className="h3">Color pattern</h3>
          <PatternTool paper={p} onApply={(a) => set((x) => { x.calibration.adjust = a })} />
        </section>

        <section className="stack">
          <h3 className="h3">Cost per sheet</h3>
          <div className="hint">Used for the running total on the wall. Leave blank to skip.</div>
          <div className="grid-2">
            {costSizes.map((s) => (
              <Field key={s} label={sizes.data?.find((z) => z.keyword === s)?.label ?? p.size_labels?.[s] ?? s}>
                <NumberInput value={p.cost_per_sheet[s] ?? 0} min={0} max={100} step={0.05} suffix={currency}
                  onChange={(v) => set((x) => { if (v) x.cost_per_sheet[s] = v; else delete x.cost_per_sheet[s] })} />
              </Field>
            ))}
          </div>
        </section>
      </div>
      {confirm === 'reset' && <Confirm title={`Reset ${p.name}?`} body="Calibration, mapping and costs return to Printmich's defaults." confirmLabel="Reset" onClose={() => setConfirm(null)}
        onConfirm={async () => { try { await api.post(`/api/papers/${p.id}/reset`); invalidate('papers'); onClose() } catch (e) { toast.error(e) } }} />}
      {confirm === 'delete' && <Confirm title={`Delete ${p.name}?`} body="Presets using it must be changed first." confirmLabel="Delete" danger onClose={() => setConfirm(null)}
        onConfirm={async () => { try { await api.del(`/api/papers/${p.id}`); invalidate('papers'); onClose() } catch (e) { toast.error(e) } }} />}
    </Drawer>
  )
}

function NewPaperDialog({ papers, onClose, onCreated }: { papers: Paper[]; onClose: () => void; onCreated: (p: Paper) => void }) {
  const [name, setName] = useState('')
  const [base, setBase] = useState('generic-heavy-fineart')
  const toast = useToast()
  return (
    <Dialog title="Add a paper" onClose={onClose} footer={
      <>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-paper" disabled={!name.trim()} onClick={async () => {
          try { const p = await api.post<Paper>('/api/papers', { name: name.trim(), base_id: base, brand: 'Third-party', code: '' }); onCreated(p) } catch (e) { toast.error(e) }
        }}>Add paper</button>
      </>
    }>
      <div className="stack">
        <Field label="Name"><input className="input" autoFocus value={name} placeholder="Hahnemühle Photo Rag 308" onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Closest Canon type" hint="Your paper starts with that type's printer mapping and calibration. Canon's own guidance lists the right type for many third-party papers.">
          <Select value={base} onChange={setBase} options={papers.map((p) => ({ value: p.id, label: p.name }))} />
        </Field>
      </div>
    </Dialog>
  )
}

function ProfilesSection() {
  const toast = useToast()
  const presets = usePresets()
  const [profiles, setProfiles] = useState<{ name: string; description: string; space: string }[]>([])
  const [targetPreset, setTargetPreset] = useState('')
  const load = () => api.get<typeof profiles>('/api/tools/profiles').then(setProfiles).catch(() => {})
  useEffect(() => { load() }, [])
  useEffect(() => { if (!targetPreset && presets.data?.length) setTargetPreset(presets.data[0].id) }, [presets.data, targetPreset])
  return (
    <section className="section">
      <div className="section-head"><h2 className="h2">Custom ICC profiles</h2></div>
      <div className="panel stack">
        <div className="prose small">
          For measured color, print a profiling target here with color management off, measure it, build a profile, then upload it and choose it in a preset. Because the target goes through the same path as your photos, the profile describes Printmich and the printer together.
        </div>
        <div className="row wrap" style={{ alignItems: 'flex-end' }}>
          <Field label="Print a target on"><Select value={targetPreset} onChange={setTargetPreset} options={(presets.data ?? []).map((x) => ({ value: x.id, label: x.name }))} /></Field>
          <label className="btn"><FileImage /> Print target file…
            <input type="file" accept=".tif,.tiff,.png,.jpg,.jpeg" hidden onChange={async (e) => {
              const f = e.target.files?.[0]
              if (!f) return
              const fd = new FormData(); fd.append('file', f); fd.append('preset_id', targetPreset)
              try { await api.post('/api/tools/target', fd); toast.ok('Target sent to the printer at actual size.') } catch (err) { toast.error(err) }
              e.target.value = ''
            }} />
          </label>
          <label className="btn"><Upload /> Upload profile…
            <input type="file" accept=".icc,.icm" hidden onChange={async (e) => {
              const f = e.target.files?.[0]
              if (!f) return
              const fd = new FormData(); fd.append('file', f)
              try { await api.post('/api/tools/profiles', fd); toast.ok('Profile uploaded.'); load() } catch (err) { toast.error(err) }
              e.target.value = ''
            }} />
          </label>
        </div>
        {profiles.length > 0 && (
          <div className="list">
            {profiles.map((pr) => (
              <div key={pr.name} className="list-row">
                <div className="grow"><div>{pr.description || pr.name}</div><div className="small faint">{pr.name}, {pr.space}</div></div>
                <button className="btn btn-ghost btn-sm" onClick={async () => { await api.del(`/api/tools/profiles/${encodeURIComponent(pr.name)}`); load() }}><Trash2 /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export function PapersPage() {
  const papers = usePapers()
  const printer = usePrinter()
  const [editing, setEditing] = useState<Paper | null>(null)
  const [adding, setAdding] = useState(false)
  const invalidate = useInvalidate()
  const list = papers.data ?? []
  const canon = list.filter((p) => p.brand === 'Canon')
  const others = list.filter((p) => p.brand !== 'Canon')
  const card = (p: Paper) => (
    <button key={p.id} className="paper-card" onClick={() => setEditing(p)}>
      <PaperSwatch paper={p} />
      <div className="stack-s" style={{ gap: 3 }}>
        <div className="row-between"><span style={{ fontWeight: 600 }}>{FINISH_LABEL[p.finish] ?? p.finish}</span>{p.customized && <span className="chip">Adjusted</span>}</div>
        <span className="small muted">{p.feeds.includes('manual') && !p.feeds.includes('top') ? 'Manual feed' : 'Top feed'}, {p.black_ink === 'matte' ? 'Matte Black' : 'Photo Black'}</span>
        {p.resolved?.media_type && <span className="small faint ellipsis">Prints as “{p.resolved.media_type.label}”</span>}
      </div>
    </button>
  )
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">Papers</h1>
          <p className="lede">Each paper carries its printer mapping and a calibration: rendering intent, sharpening and color corrections. Tune them once with a chart or color pattern and every preset benefits.</p>
        </div>
        <div className="actions"><button className="btn" onClick={() => setAdding(true)}><Plus /> Add a paper</button></div>
      </header>
      {!printer.data?.configured && <div style={{ marginBottom: 18 }}><Empty title="Connect a printer to see how papers map to its media types" /></div>}
      {papers.isLoading ? <Loading /> : (
        <>
          <section><div className="section-head"><h2 className="h2">Canon papers</h2></div><div className="paper-grid">{canon.map(card)}</div></section>
          <section className="section"><div className="section-head"><h2 className="h2">Other papers</h2></div><div className="paper-grid">{others.map(card)}</div></section>
        </>
      )}
      <ProfilesSection />
      {editing && <PaperEditor initial={editing} onClose={() => setEditing(null)} />}
      {adding && <NewPaperDialog papers={list} onClose={() => setAdding(false)} onCreated={(p) => { setAdding(false); invalidate('papers'); setEditing(p) }} />}
    </div>
  )
}

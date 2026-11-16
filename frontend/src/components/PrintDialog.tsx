import { useEffect, useMemo, useState, type MouseEvent } from 'react'
import { Crosshair, Printer, RotateCcw } from 'lucide-react'
import { api } from '../lib/api'
import { usePapers, usePresets, useRenderPreview, useSizes } from '../lib/hooks'
import type { AssetSummary, Preset, RenderInfo } from '../lib/types'
import { fmtDate, photoTitle, place, takenDate } from '../lib/format'
import { Dialog, Field, NumberInput, Select, Spinner, Toggle, useToast } from './ui'
import { PrintSheet } from './PrintSheet'

function clamp01(v: number) { return Math.min(1, Math.max(0, v)) }

/** Convert a click on the rendered page into a focus point in source-image coordinates. */
export function focusFromClick(e: MouseEvent<HTMLDivElement>, info: RenderInfo): [number, number] | null {
  const rect = e.currentTarget.getBoundingClientRect()
  const u = (e.clientX - rect.left) / rect.width
  const v = (e.clientY - rect.top) / rect.height
  const g = info.geometry
  const lw = (g.layout_mm[0] / 25.4) * g.dpi
  const lh = (g.layout_mm[1] / 25.4) * g.dpi
  const s = (u - g.photo_offset_px[0] / lw) / (g.photo_px[0] / lw)
  const t = (v - g.photo_offset_px[1] / lh) / (g.photo_px[1] / lh)
  if (s < 0 || s > 1 || t < 0 || t > 1) return null
  const c = info.crop
  return [clamp01(c.x + s * c.w), clamp01(c.y + t * c.h)]
}

export function focusToPage(info: RenderInfo): { left: string; top: string } | null {
  const g = info.geometry
  const c = info.crop
  if (!c || c.method === 'fit') return null
  const lw = (g.layout_mm[0] / 25.4) * g.dpi
  const lh = (g.layout_mm[1] / 25.4) * g.dpi
  const s = (c.focus[0] - c.x) / c.w
  const t = (c.focus[1] - c.y) / c.h
  const u = (g.photo_offset_px[0] + s * g.photo_px[0]) / lw
  const v = (g.photo_offset_px[1] + t * g.photo_px[1]) / lh
  return { left: `${clamp01(u) * 100}%`, top: `${clamp01(v) * 100}%` }
}

export function ppiVerdict(ppi: number | null | undefined) {
  if (!ppi) return null
  if (ppi >= 280) return { label: 'Excellent detail', cls: 'chip-ok' }
  if (ppi >= 200) return { label: 'Good detail', cls: 'chip-ok' }
  if (ppi >= 150) return { label: 'Acceptable', cls: 'chip-warn' }
  return { label: 'Too soft for this size', cls: 'chip-err' }
}

export function PrintDialog({ asset, onClose, initialPresetId }: { asset: AssetSummary; onClose: () => void; initialPresetId?: string | null }) {
  const presets = usePresets()
  const papers = usePapers()
  const sizes = useSizes()
  const toast = useToast()
  const [presetId, setPresetId] = useState<string | null>(initialPresetId ?? null)
  const [draft, setDraft] = useState<Preset | null>(null)
  const [focus, setFocus] = useState<[number, number] | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!presets.data?.length) return
    if (draft && draft.id === presetId) return
    const p = presets.data.find((x) => x.id === presetId) ?? presets.data[0]
    setPresetId(p.id)
    setDraft(structuredClone(p))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets.data, presetId])

  const preview = useRenderPreview(draft ? { asset_id: asset.id, preset: draft, focus } : null, [], 160)
  const info = preview.info
  const paper = papers.data?.find((p) => p.id === draft?.output.paper_id)
  const aspect = info ? info.geometry.layout_mm[0] / info.geometry.layout_mm[1] : 2 / 3
  const dot = info ? focusToPage(info) : null
  const verdict = ppiVerdict(info?.effective_ppi)

  const set = (fn: (p: Preset) => void) => setDraft((d) => {
    if (!d) return d
    const n = structuredClone(d)
    fn(n)
    return n
  })

  const sizeOptions = useMemo(() => (sizes.data ?? []).map((s) => ({ value: s.keyword, label: s.label })), [sizes.data])

  async function print() {
    if (!draft) return
    setBusy(true)
    try {
      await api.post('/api/prints', { asset_id: asset.id, preset: draft, focus })
      toast.ok(<>Sent <strong>{photoTitle(asset)}</strong> to the print queue.</>)
      onClose()
    } catch (e) {
      toast.error(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog onClose={onClose} wide labelledBy="print-title">
      <div className="print-stage">
        {draft && (
          <div style={{ position: 'relative', width: '100%', display: 'grid', placeItems: 'center' }}>
            <PrintSheet src={preview.url} aspect={aspect} finish={paper?.finish} sheen={paper?.sheen} tint={paper?.tint}
              maxHeight="var(--stage-h)"
              onClick={(e) => { if (info) { const f = focusFromClick(e, info); if (f) setFocus(f) } }}>
              {dot && <span className="focus-dot" style={dot} />}
              {preview.loading && !preview.url && <div className="sheet-loading"><Spinner /></div>}
            </PrintSheet>
          </div>
        )}
        <div className="row small faint stage-hint">
          <Crosshair size={14} /> Click the photo to choose what stays in frame
          {focus && <button className="btn btn-ghost btn-sm" onClick={() => setFocus(null)}><RotateCcw /> Auto</button>}
          {preview.loading && preview.url && <Spinner size={14} />}
        </div>
      </div>
      <div className="print-side">
        <div className="print-side-body">
          <div>
            <h2 className="h2" id="print-title">{photoTitle(asset)}</h2>
            <div className="small muted">{[place(asset), fmtDate(takenDate(asset))].filter(Boolean).join(', ')}</div>
          </div>
          {presets.data && draft && (
            <>
              <Field label="Preset">
                <Select value={presetId ?? ''} onChange={(v) => { setPresetId(v); setFocus(null) }}
                  options={presets.data.map((p) => ({ value: p.id, label: p.name }))} />
              </Field>
              <Field label="Paper">
                <Select value={draft.output.paper_id} onChange={(v) => set((p) => { p.output.paper_id = v })}
                  options={(papers.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
              </Field>
              <Field label="Size">
                <Select value={draft.output.media_size} onChange={(v) => set((p) => { p.output.media_size = v })}
                  options={sizeOptions.length ? sizeOptions : [{ value: draft.output.media_size, label: draft.size_label ?? draft.output.media_size }]} />
              </Field>
              <div className="stack-s">
                <Toggle checked={draft.layout.borderless} onChange={(v) => set((p) => { p.layout.borderless = v })} label="Borderless" />
                <Toggle checked={draft.layout.caption.enabled} disabled={draft.layout.borderless}
                  onChange={(v) => set((p) => { p.layout.caption.enabled = v })} label="Caption under the photo"
                  hint={draft.layout.borderless ? 'Needs a border' : info?.caption || undefined} />
                <Toggle checked={draft.color.mode !== 'color'} onChange={(v) => set((p) => { p.color.mode = v ? 'bw' : 'color' })} label="Black & white" />
              </div>
              <Field label="Copies">
                <NumberInput value={draft.output.copies} min={1} max={20} onChange={(v) => set((p) => { p.output.copies = v })} width={90} />
              </Field>
            </>
          )}
          {info && (
            <div className="stack-s">
              <hr className="divider" style={{ margin: '4px 0' }} />
              <dl className="kv">
                <dt>Sheet</dt><dd>{info.plan.page_label}{info.plan.borderless ? ', borderless' : ''}</dd>
                <dt>Printer paper type</dt><dd>{info.plan.media_type_label}</dd>
                <dt>Feed</dt><dd>{info.plan.media_source_label}</dd>
                <dt>Output</dt><dd>{info.plan.summary}</dd>
                {info.effective_ppi ? (<><dt>Detail</dt><dd className="row" style={{ gap: 8 }}>
                  <span className="num">{Math.round(info.effective_ppi)} ppi</span>
                  {verdict && <span className={`chip ${verdict.cls}`}>{verdict.label}</span>}
                </dd></>) : null}
              </dl>
              {info.warnings.map((w) => <div key={w} className="small" style={{ color: 'var(--warn)' }}>{w}</div>)}
              {preview.error && <div className="small" style={{ color: 'var(--err)' }}>{preview.error}</div>}
            </div>
          )}
        </div>
        <div className="print-side-foot">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-paper grow" onClick={print} disabled={busy || !draft}>
            <Printer /> {draft && draft.output.copies > 1 ? `Print ${draft.output.copies} copies` : 'Print'}
          </button>
        </div>
      </div>
    </Dialog>
  )
}

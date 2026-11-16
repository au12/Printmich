import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Palette, RotateCcw, Ruler, ScanLine, ShieldCheck, SlidersHorizontal, Trash2, Type } from 'lucide-react'
import { api, thumbUrl } from '../lib/api'
import { useBrowse, usePapers, usePrinter, useRenderPreview, useSettings, useSizes } from '../lib/hooks'
import type { Adjustments, Margins, Preset } from '../lib/types'
import { round } from '../lib/format'
import { Field, Group, NumberInput, Segmented, Select, Slider, Spinner, Toggle, useToast } from './ui'
import { PrintSheet } from './PrintSheet'
import { focusFromClick, focusToPage, ppiVerdict } from './PrintDialog'

const BORDER_STYLES: { key: string; label: string; m: Margins }[] = [
  { key: 'thin', label: 'Thin', m: { top: 5, right: 5, bottom: 5, left: 5 } },
  { key: 'classic', label: 'Classic', m: { top: 12, right: 12, bottom: 12, left: 12 } },
  { key: 'gallery', label: 'Gallery mat', m: { top: 25, right: 25, bottom: 32, left: 25 } },
  { key: 'instant', label: 'Instant', m: { top: 6, right: 6, bottom: 26, left: 6 } },
]

const TOKENS = ['{place}', '{date:%B %Y}', '{date}', '{year}', '{description}', '{camera}', '{exposure}', '{people}', '{city}', '{country}']

const ADJ: { key: keyof Adjustments; label: string; track?: string }[] = [
  { key: 'brightness', label: 'Brightness', track: 'linear-gradient(90deg, #2a2a2a, #d8d8d8)' },
  { key: 'contrast', label: 'Contrast' },
  { key: 'saturation', label: 'Intensity', track: 'linear-gradient(90deg, #8a8a8a, #e2007a)' },
  { key: 'shadows', label: 'Shadows' },
  { key: 'highlights', label: 'Highlights' },
  { key: 'cyan', label: 'Cyan', track: 'linear-gradient(90deg, #e4002b, #888 50%, #00a3e0)' },
  { key: 'magenta', label: 'Magenta', track: 'linear-gradient(90deg, #2bb24c, #888 50%, #e2007a)' },
  { key: 'yellow', label: 'Yellow', track: 'linear-gradient(90deg, #2f5bd3, #888 50%, #ffdd00)' },
]

function ToneMat({ x, y, onChange }: { x: number; y: number; onChange: (x: number, y: number) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const set = (e: MouseEvent<HTMLDivElement>) => {
    const r = ref.current!.getBoundingClientRect()
    const nx = Math.round((((e.clientX - r.left) / r.width) * 200 - 100) / 5) * 5
    const ny = Math.round((50 - ((e.clientY - r.top) / r.height) * 100) / 5) * 5
    onChange(Math.max(-100, Math.min(100, nx)), Math.max(-50, Math.min(50, ny)))
  }
  return (
    <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
      <div ref={ref} className="tone-pad" onMouseDown={set} onMouseMove={(e) => { if (e.buttons === 1) set(e) }} role="slider"
        aria-label="Black and white tone" aria-valuetext={`X ${x}, Y ${y}`} tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') onChange(Math.max(-100, x - 5), y)
          if (e.key === 'ArrowRight') onChange(Math.min(100, x + 5), y)
          if (e.key === 'ArrowUp') onChange(x, Math.min(50, y + 5))
          if (e.key === 'ArrowDown') onChange(x, Math.max(-50, y - 5))
        }}>
        <span className="knob" style={{ left: `${((x + 100) / 200) * 100}%`, top: `${((50 - y) / 100) * 100}%` }} />
      </div>
      <div className="small muted stack-s">
        <span>Left is cooler, right is warmer.</span>
        <span>Up adds magenta, down adds green.</span>
        <span className="num">X {x > 0 ? `+${x}` : x}, Y {y > 0 ? `+${y}` : y}</span>
      </div>
    </div>
  )
}

export function PresetEditor({ value, onChange, onSave, onDelete, onDuplicate, dirty }: {
  value: Preset
  onChange: (p: Preset) => void
  onSave: () => void
  onDelete?: () => void
  onDuplicate?: () => void
  dirty: boolean
}) {
  const p = value
  const papers = usePapers()
  const sizes = useSizes()
  const printer = usePrinter()
  const settings = useSettings()
  const toast = useToast()
  const favs = useBrowse('favorites')
  const samples = useMemo(() => favs.data?.pages[0]?.items.slice(0, 18) ?? [], [favs.data])
  const [sampleId, setSampleId] = useState<string | null>(null)
  const [focus, setFocus] = useState<[number, number] | null>(null)
  const [profiles, setProfiles] = useState<{ name: string; path: string; description: string }[]>([])
  const [validating, setValidating] = useState(false)
  const units = settings.data?.units ?? 'in'

  useEffect(() => { if (!sampleId && samples.length) setSampleId(samples[0].id) }, [samples, sampleId])
  useEffect(() => { api.get<typeof profiles>('/api/tools/profiles').then(setProfiles).catch(() => {}) }, [])

  const preview = useRenderPreview(sampleId ? { asset_id: sampleId, preset: p, focus } : null, [], 260)
  const info = preview.info
  const paper = papers.data?.find((x) => x.id === p.output.paper_id)
  const caps = printer.data?.capabilities
  const aspect = info ? info.geometry.layout_mm[0] / info.geometry.layout_mm[1] : 2 / 3
  const dot = info ? focusToPage(info) : null
  const verdict = ppiVerdict(info?.effective_ppi)

  const set = (fn: (x: Preset) => void) => { const n = structuredClone(p); fn(n); onChange(n) }
  const toMm = (v: number) => (units === 'in' ? v * 25.4 : v)
  const fromMm = (v: number) => (units === 'in' ? round(v / 25.4, 3) : round(v, 1))
  const borderStyle = BORDER_STYLES.find((b) => (['top', 'right', 'bottom', 'left'] as const).every((k) => Math.abs(b.m[k] - p.layout.margins[k]) < 0.1))?.key ?? 'custom'

  async function validate() {
    setValidating(true)
    try {
      const r = await api.post<{ ok: boolean; status: string; message: string; unsupported: string[] }>('/api/presets/validate', { preset: p })
      if (r.ok && !r.unsupported.length) toast.ok('The printer accepts these settings.')
      else toast.err(`Printer replied ${r.status}${r.unsupported.length ? `; unsupported: ${r.unsupported.join(', ')}` : ''}${r.message ? ` (${r.message})` : ''}`)
    } catch (e) { toast.error(e) } finally { setValidating(false) }
  }

  const cal = paper?.calibration.adjust
  const calText = cal ? Object.entries(cal).filter(([, v]) => v).map(([k, v]) => `${k} ${v > 0 ? '+' : ''}${v}`).join(', ') : ''

  return (
    <div className="editor">
      <div className="editor-preview stack">
        <div className="table editor-table">
          <div style={{ width: '100%', display: 'grid', placeItems: 'center' }}>
            <PrintSheet src={preview.url} aspect={aspect} finish={paper?.finish} sheen={paper?.sheen} tint={paper?.tint} maxHeight="var(--editor-h)"
              onClick={(e) => { if (info) { const f = focusFromClick(e, info); if (f) setFocus(f) } }}>
              {dot && <span className="focus-dot" style={dot} />}
              {!preview.url && <div className="sheet-loading">{sampleId ? <Spinner /> : <span className="small faint">Connect Immich to preview with your photos</span>}</div>}
            </PrintSheet>
          </div>
          {preview.loading && preview.url && <span style={{ position: 'absolute', top: 14, right: 14 }}><Spinner size={14} /></span>}
        </div>
        {samples.length > 0 && (
          <div className="row" style={{ gap: 6, overflowX: 'auto', paddingBottom: 4, flexWrap: 'nowrap', minWidth: 0 }} aria-label="Sample photo">
            {samples.map((s) => (
              <button key={s.id} onClick={() => { setSampleId(s.id); setFocus(null) }} title={s.filename}
                style={{ flex: 'none', width: 46, height: 46, padding: 0, border: s.id === sampleId ? '2px solid var(--text)' : '2px solid transparent', borderRadius: 4, overflow: 'hidden', cursor: 'pointer', background: 'var(--g2)' }}>
                <img src={thumbUrl(s.id)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              </button>
            ))}
          </div>
        )}
        {info && (
          <div className="panel panel-tight">
            <dl className="kv">
              <dt>Sends</dt><dd>{info.plan.summary}</dd>
              <dt>Printer paper type</dt><dd>{info.plan.media_type_label} <span className="faint small">({info.plan.media_type_how === 'hint' ? 'matched by name' : info.plan.media_type_how === 'generic' ? 'closest standard type' : info.plan.media_type_how})</span></dd>
              <dt>Feed</dt><dd>{info.plan.media_source_label}</dd>
              <dt>Quality</dt><dd>{info.plan.quality === 'high' ? 'Highest' : info.plan.quality === 'normal' ? 'Standard' : 'Fast'}{info.plan.rendering_intent_ipp ? `, ${info.plan.rendering_intent_ipp} intent` : ''}</dd>
              <dt>Photo area</dt><dd className="num">{units === 'in' ? `${round(info.geometry.photo_mm[0] / 25.4, 2)} × ${round(info.geometry.photo_mm[1] / 25.4, 2)} in` : `${round(info.geometry.photo_mm[0])} × ${round(info.geometry.photo_mm[1])} mm`}</dd>
              {info.effective_ppi ? (<><dt>Detail</dt><dd className="row" style={{ gap: 8 }}><span className="num">{Math.round(info.effective_ppi)} ppi</span>{verdict && <span className={`chip ${verdict.cls}`}>{verdict.label}</span>}</dd></>) : null}
              {info.caption && (<><dt>Caption</dt><dd>{info.caption}</dd></>)}
            </dl>
            {info.warnings.map((w) => <div key={w} className="small" style={{ color: 'var(--warn)', marginTop: 8 }}>{w}</div>)}
          </div>
        )}
        {preview.error && <div className="small" style={{ color: 'var(--err)' }}>{preview.error}</div>}
      </div>

      <div className="stack-s">
        <div className="panel panel-tight stack">
          <Field label="Preset name"><input className="input" value={p.name} onChange={(e) => set((x) => { x.name = e.target.value })} /></Field>
          <Field label="Description"><input className="input" value={p.description} placeholder="What this preset is for" onChange={(e) => set((x) => { x.description = e.target.value })} /></Field>
        </div>

        <Group title="Paper" icon={<Ruler size={16} />} defaultOpen summary={`${paper?.name ?? ''}, ${sizes.data?.find((s) => s.keyword === p.output.media_size)?.label ?? p.output.media_size}`}>
          <Field label="Paper" hint={paper ? <>{paper.notes} <Link to="/papers">Calibrate</Link></> : undefined}>
            <Select value={p.output.paper_id} onChange={(v) => set((x) => {
              x.output.paper_id = v
              const np = papers.data?.find((y) => y.id === v)
              if (np && !np.borderless) x.layout.borderless = false
              if (np?.recommended_margins && !x.layout.borderless) x.layout.margins = { ...np.recommended_margins }
            })}
              options={(papers.data ?? []).map((x) => ({ value: x.id, label: `${x.name}${x.code ? ` (${x.code})` : ''}` }))} />
          </Field>
          <div className="grid-2">
            <Field label="Size">
              <Select value={p.output.media_size} onChange={(v) => set((x) => { x.output.media_size = v })}
                options={(sizes.data ?? [{ keyword: p.output.media_size, label: p.output.media_size }]).map((s) => ({ value: s.keyword, label: s.label }))} />
            </Field>
            <Field label="Feed">
              <Select value={p.output.media_source} onChange={(v) => set((x) => { x.output.media_source = v })}
                options={[{ value: 'auto', label: `Automatic${paper ? ` (${paper.default_feed === 'manual' ? 'manual feed' : 'top feed'})` : ''}` },
                  ...(caps?.sources ?? []).map((s) => ({ value: s.keyword, label: s.label }))]} />
            </Field>
          </div>
          <Field label="Printer paper type" hint="Automatic maps this paper to the closest media type your printer offers.">
            <Select value={p.output.media_type} onChange={(v) => set((x) => { x.output.media_type = v })}
              options={[{ value: 'auto', label: `Automatic${paper?.resolved?.media_type?.label ? ` (${paper.resolved.media_type.label})` : ''}` },
                ...(caps?.types ?? []).map((t) => ({ value: t.keyword, label: t.label }))]} />
          </Field>
          <Field label="Copies"><NumberInput value={p.output.copies} min={1} max={99} onChange={(v) => set((x) => { x.output.copies = v })} width={90} /></Field>
        </Group>

        <Group title="Layout" icon={<ScanLine size={16} />} defaultOpen summary={p.layout.borderless ? 'Borderless' : `Border ${borderStyle}`}>
          <Toggle checked={p.layout.borderless} onChange={(v) => set((x) => { x.layout.borderless = v })} label="Borderless"
            hint={paper && !paper.borderless ? `${paper.name} isn't rated for borderless.` : 'The printer extends the image slightly past the edges.'} />
          {!p.layout.borderless && (
            <>
              <Segmented value={borderStyle} onChange={(k) => { const b = BORDER_STYLES.find((x) => x.key === k); if (b) set((x) => { x.layout.margins = { ...b.m } }) }}
                options={[...BORDER_STYLES.map((b) => ({ value: b.key, label: b.label })), { value: 'custom', label: 'Custom' }]} />
              <div className="grid-4">
                {(['top', 'right', 'bottom', 'left'] as const).map((k) => (
                  <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
                    <NumberInput value={fromMm(p.layout.margins[k])} min={0} max={units === 'in' ? 8 : 200} step={units === 'in' ? 0.125 : 1}
                      onChange={(v) => set((x) => { x.layout.margins[k] = round(toMm(v), 2) })} suffix={units} />
                  </Field>
                ))}
              </div>
              {paper?.recommended_margins && <div className="hint">Canon recommends at least {fromMm(paper.recommended_margins.top)} {units} top and bottom margins on {paper.name}.</div>}
              <Toggle checked={p.layout.keyline} onChange={(v) => set((x) => { x.layout.keyline = v })} label="Thin keyline around the photo" />
            </>
          )}
          <div className="grid-2">
            <Field label="Fit">
              <Segmented value={p.layout.fit} onChange={(v) => set((x) => { x.layout.fit = v })} block
                options={[{ value: 'fill', label: 'Fill (crop)' }, { value: 'fit', label: 'Whole photo' }]} />
            </Field>
            <Field label="Orientation">
              <Select value={p.layout.orientation} onChange={(v) => set((x) => { x.layout.orientation = v })}
                options={[{ value: 'auto', label: 'Match the photo' }, { value: 'portrait', label: 'Always portrait' }, { value: 'landscape', label: 'Always landscape' }]} />
            </Field>
          </div>
          {p.layout.fit === 'fill' && (
            <Field label="When cropping, keep in frame" hint="Faces come from Immich's face detection (needs the face.read permission).">
              <Select value={p.layout.crop} onChange={(v) => set((x) => { x.layout.crop = v })}
                options={[{ value: 'smart', label: 'Faces, then the most interesting area' }, { value: 'faces', label: 'Faces, else the center' },
                  { value: 'attention', label: 'The most interesting area' }, { value: 'center', label: 'The center' }]} />
            </Field>
          )}
        </Group>

        <Group title="Caption" icon={<Type size={16} />} summary={p.layout.caption.enabled && !p.layout.borderless ? p.layout.caption.template : 'Off'}>
          <Toggle checked={p.layout.caption.enabled} disabled={p.layout.borderless} onChange={(v) => set((x) => { x.layout.caption.enabled = v })}
            label="Print a caption under the photo" hint={p.layout.borderless ? 'Turn off borderless to add a caption.' : undefined} />
          {p.layout.caption.enabled && !p.layout.borderless && (
            <>
              <Field label="Text" hint="Empty values drop out with their separator, so photos without a location still read cleanly.">
                <input className="input" value={p.layout.caption.template} onChange={(e) => set((x) => { x.layout.caption.template = e.target.value })} />
              </Field>
              <div className="row wrap" style={{ gap: 6 }}>
                {TOKENS.map((t) => (
                  <button key={t} type="button" className="chip" style={{ cursor: 'pointer', background: 'none' }}
                    onClick={() => set((x) => { x.layout.caption.template = `${x.layout.caption.template}${x.layout.caption.template ? ', ' : ''}${t}` })}>{t}</button>
                ))}
              </div>
              <div className="grid-2">
                <Field label="Typeface">
                  <Segmented value={p.layout.caption.font} onChange={(v) => set((x) => { x.layout.caption.font = v })} block
                    options={[{ value: 'serif', label: 'Garamond' }, { value: 'sans', label: 'Inter' }, { value: 'mono', label: 'Mono' }]} />
                </Field>
                <Field label="Alignment">
                  <Segmented value={p.layout.caption.align} onChange={(v) => set((x) => { x.layout.caption.align = v })} block
                    options={[{ value: 'left', label: 'Left' }, { value: 'center', label: 'Center' }, { value: 'right', label: 'Right' }]} />
                </Field>
              </div>
              <div className="grid-2">
                <Slider label="Size" value={p.layout.caption.size_pt} min={5} max={24} step={0.5} format={(v) => `${v} pt`} onChange={(v) => set((x) => { x.layout.caption.size_pt = v })} />
                <Slider label="Letter spacing" value={Math.round(p.layout.caption.letter_spacing * 100)} min={0} max={40} format={(v) => `${v}%`} onChange={(v) => set((x) => { x.layout.caption.letter_spacing = v / 100 })} />
              </div>
              <div className="row" style={{ gap: 18 }}>
                <Toggle checked={p.layout.caption.italic} onChange={(v) => set((x) => { x.layout.caption.italic = v })} label="Italic" />
                <label className="row small muted">Color <input type="color" value={p.layout.caption.color} onChange={(e) => set((x) => { x.layout.caption.color = e.target.value })} style={{ width: 36, height: 26, border: 0, background: 'none' }} /></label>
              </div>
            </>
          )}
        </Group>

        <Group title="Color" icon={<Palette size={16} />} summary={`${p.color.mode === 'color' ? 'Color' : p.color.mode === 'bw' ? 'Black & white' : 'Toned B&W'}, ${p.color.space === 'auto' ? 'auto gamut' : p.color.space === 'srgb' ? 'sRGB' : 'Adobe RGB'}`}>
          <Segmented value={p.color.mode} onChange={(v) => set((x) => { x.color.mode = v })} block
            options={[{ value: 'color', label: 'Color' }, { value: 'bw', label: 'Black & white' }, { value: 'bw-toned', label: 'Toned B&W' }]} />
          {p.color.mode === 'bw' && <div className="hint">Sent as grayscale so the PRO-310 prints with its gray and black inks for neutral tones.</div>}
          {p.color.mode === 'bw-toned' && (
            <>
              <Segmented value={p.color.tone.preset} onChange={(v) => set((x) => { x.color.tone.preset = v })}
                options={[{ value: 'cool', label: 'Cool' }, { value: 'neutral', label: 'Neutral' }, { value: 'warm', label: 'Warm' }, { value: 'custom', label: 'Custom' }]} />
              {p.color.tone.preset === 'custom' && <ToneMat x={p.color.tone.x} y={p.color.tone.y} onChange={(nx, ny) => set((x) => { x.color.tone.x = nx; x.color.tone.y = ny })} />}
            </>
          )}
          <div className="grid-2">
            <Field label="Gamut sent to the printer" hint={caps && !caps.pwg_types.some((t) => t.startsWith('adobe-rgb')) ? 'Your printer only offers sRGB.' : 'Automatic uses Adobe RGB for wide-gamut photos (e.g. iPhone Display P3).'}>
              <Select value={p.color.space} onChange={(v) => set((x) => { x.color.space = v })}
                options={[{ value: 'auto', label: 'Automatic' }, { value: 'srgb', label: 'sRGB' }, { value: 'adobe-rgb', label: 'Adobe RGB (1998)' }]} />
            </Field>
            <Field label="Rendering intent" hint={`Paper default: ${paper?.calibration.intent ?? ''}.`}>
              <Select value={p.color.intent} onChange={(v) => set((x) => { x.color.intent = v })}
                options={[{ value: 'paper', label: 'Paper default' }, { value: 'perceptual', label: 'Perceptual' }, { value: 'relative', label: 'Relative colorimetric' },
                  { value: 'saturation', label: 'Saturation' }, { value: 'absolute', label: 'Absolute colorimetric' }]} />
            </Field>
          </div>
          <Toggle checked={p.color.bpc} onChange={(v) => set((x) => { x.color.bpc = v })} label="Black point compensation" hint="Keeps shadow detail when the paper's black is lighter than the photo's." />
          <Toggle checked={p.color.send_rendering_intent} onChange={(v) => set((x) => { x.color.send_rendering_intent = v })} label="Tell the printer which intent to use"
            hint={caps?.rendering_intents?.length ? `Supported: ${caps.rendering_intents.join(', ')}.` : 'Ignored if the printer doesn’t support it.'} />
          <Field label="Color management">
            <Select value={p.color.management} onChange={(v) => set((x) => { x.color.management = v })}
              options={[{ value: 'managed', label: 'Printmich (recommended)' }, { value: 'custom-icc', label: 'My own ICC profile' }, { value: 'passthrough', label: 'Off, for profiling targets' }]} />
          </Field>
          {p.color.management === 'custom-icc' && (
            <Field label="ICC profile" hint={<>Use a profile measured through Printmich (closed loop). Upload profiles under <Link to="/papers">Papers</Link>.</>}>
              <Select value={p.color.icc_profile ?? ''} onChange={(v) => set((x) => { x.color.icc_profile = v || null })}
                options={[{ value: '', label: profiles.length ? 'Choose a profile' : 'No profiles uploaded' }, ...profiles.map((pr) => ({ value: pr.path, label: pr.description || pr.name }))]} />
            </Field>
          )}
          {p.color.management === 'passthrough' && <div className="hint">No conversion, adjustments or sharpening — use only for printing measurement targets.</div>}
        </Group>

        <Group title="Adjustments" icon={<SlidersHorizontal size={16} />} summary={Object.values(p.adjust).some(Boolean) ? 'Customised' : 'None'}>
          <div className="hint">Applied on top of the paper calibration{calText ? ` (${paper?.name}: ${calText})` : ''}. Double-click a slider to reset it.</div>
          {ADJ.map((a) => (
            <Slider key={a.key} label={a.label} value={p.adjust[a.key]} min={-50} max={50} track={a.track}
              onChange={(v) => set((x) => { x.adjust[a.key] = v })} />
          ))}
          <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }}
            onClick={() => set((x) => { (Object.keys(x.adjust) as (keyof Adjustments)[]).forEach((k) => { x.adjust[k] = 0 }) })}><RotateCcw /> Reset adjustments</button>
        </Group>

        <Group title="Quality & output" icon={<ShieldCheck size={16} />} summary={`${p.output.quality === 'high' ? 'Highest' : p.output.quality === 'normal' ? 'Standard' : 'Fast'}, ${p.output.resolution ? `${p.output.resolution} dpi` : 'auto dpi'}`}>
          <Field label="Print quality">
            <Segmented value={p.output.quality} onChange={(v) => set((x) => { x.output.quality = v })} block
              options={[{ value: 'high', label: 'Highest' }, { value: 'normal', label: 'Standard' }, { value: 'draft', label: 'Fast' }]} />
          </Field>
          <div className="grid-2">
            <Field label="Resolution" hint="Pixels Printmich renders per inch. 600 dpi suits the PRO-310's photo modes.">
              <Select value={p.output.resolution} onChange={(v) => set((x) => { x.output.resolution = v })}
                options={[{ value: 0, label: 'Automatic' }, ...((caps?.pwg_resolutions?.length ? caps.pwg_resolutions : [300, 600])).map((r) => ({ value: r, label: `${r} dpi` }))]} />
            </Field>
            <Field label="Output sharpening" hint={`Paper default: ${paper?.calibration.sharpening ?? ''}.`}>
              <Select value={p.output.sharpening} onChange={(v) => set((x) => { x.output.sharpening = v })}
                options={[{ value: 'paper', label: 'Paper default' }, { value: 'off', label: 'Off' }, { value: 'low', label: 'Low' }, { value: 'standard', label: 'Standard' }, { value: 'high', label: 'High' }]} />
            </Field>
            <Field label="Document format">
              <Select value={p.output.document_format} onChange={(v) => set((x) => { x.output.document_format = v })}
                options={[{ value: 'auto', label: 'Automatic' }, { value: 'pwg', label: 'PWG raster (exact pixels)' }, { value: 'jpeg', label: 'JPEG' }]} />
            </Field>
            <Field label="Bit depth">
              <Segmented value={p.output.bit_depth} onChange={(v) => set((x) => { x.output.bit_depth = v })} block
                options={[{ value: 8, label: '8-bit' }, { value: 16, label: '16-bit' }]} />
            </Field>
          </div>
          <Field label="Extra printer settings" hint="Advanced: one IPP job attribute per line, like print-content-optimize=photo.">
            <textarea className="textarea" spellCheck={false} rows={3}
              value={Object.entries(p.output.extra_ipp).map(([k, v]) => `${k}=${v}`).join('\n')}
              onChange={(e) => set((x) => {
                const out: Record<string, string | number | boolean> = {}
                e.target.value.split('\n').forEach((line) => {
                  const [k, ...rest] = line.split('=')
                  const val = rest.join('=').trim()
                  if (!k?.trim() || !val) return
                  out[k.trim()] = /^\d+$/.test(val) ? Number(val) : val === 'true' ? true : val === 'false' ? false : val
                })
                x.output.extra_ipp = out
              })} />
          </Field>
          <div className="hint">Drying time, head height and borderless extension are stored on the printer per paper type. Set them on the PRO-310 under Printer settings, Paper-related settings.</div>
        </Group>

        <div className="row-between" style={{ marginTop: 10, position: 'sticky', bottom: 0, padding: '12px 0', background: 'var(--g1)' }}>
          <div className="row" style={{ gap: 4 }}>
            {onDuplicate && <button className="btn btn-ghost btn-icon btn-sm" onClick={onDuplicate} title="Duplicate preset" aria-label="Duplicate preset"><Copy /></button>}
            {onDelete && <button className="btn btn-ghost btn-icon btn-sm btn-danger" onClick={onDelete} title="Delete preset" aria-label="Delete preset"><Trash2 /></button>}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn" onClick={validate} disabled={validating || !printer.data?.configured} title="Ask the printer whether it accepts these settings">
              {validating ? <Spinner size={14} /> : <ShieldCheck />} Check with printer
            </button>
            <button className="btn btn-paper" onClick={onSave} disabled={!dirty}>Save preset</button>
          </div>
        </div>
      </div>
    </div>
  )
}

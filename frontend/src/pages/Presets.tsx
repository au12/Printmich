import { useState } from 'react'
import { ArrowLeft, Plus, SlidersHorizontal } from 'lucide-react'
import { api } from '../lib/api'
import { useInvalidate, usePapers, usePresets, useSizes } from '../lib/hooks'
import type { Preset } from '../lib/types'
import { PresetEditor } from '../components/PresetEditor'
import { Confirm, Empty, Loading, useToast } from '../components/ui'

export function PageSwatch({ preset, w, h, tint }: { preset: Preset; w: number; h: number; tint?: string }) {
  const landscapeSheet = false
  const W = landscapeSheet ? h : w
  const H = landscapeSheet ? w : h
  const m = preset.layout.borderless ? { top: 0, right: 0, bottom: 0, left: 0 } : preset.layout.margins
  const scale = 56 / Math.max(W, H)
  return (
    <div style={{ width: W * scale, height: H * scale, background: tint ?? '#fbfbf9', boxShadow: '0 1px 2px rgba(0,0,0,.4), 0 6px 14px -6px rgba(0,0,0,.5)', position: 'relative' }}>
      <div style={{
        position: 'absolute', left: m.left * scale, top: m.top * scale, right: m.right * scale, bottom: m.bottom * scale,
        background: preset.color.mode === 'color' ? 'linear-gradient(160deg, #79a7c9, #3f6f5c 55%, #c9a36b)' : 'linear-gradient(160deg, #bdbdbd, #4a4a4a 60%, #9a9a9a)',
      }} />
      {preset.layout.caption.enabled && !preset.layout.borderless && (
        <div style={{ position: 'absolute', left: '30%', right: '30%', bottom: Math.max(2, (m.bottom * scale) / 2 - 1), height: 1.5, background: 'rgba(0,0,0,.35)' }} />
      )}
    </div>
  )
}

export function PresetsPage() {
  const presets = usePresets()
  const papers = usePapers()
  const sizes = useSizes()
  const invalidate = useInvalidate()
  const toast = useToast()
  const [editing, setEditing] = useState<Preset | null>(null)
  const [original, setOriginal] = useState<string>('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  const open = (p: Preset) => { setEditing(structuredClone(p)); setOriginal(JSON.stringify(p)) }

  async function save() {
    if (!editing) return
    try {
      const saved = await api.put<Preset>(`/api/presets/${editing.id}`, editing as unknown as Record<string, unknown>)
      toast.ok(`Saved “${saved.name}”.`)
      setOriginal(JSON.stringify(editing))
      invalidate('presets', 'dashboard', 'schedules')
    } catch (e) { toast.error(e) }
  }

  async function create() {
    const base = presets.data?.[0]
    try {
      const p = await api.post<Preset>('/api/presets', { ...(base ? structuredClone(base) : {}), name: 'New preset', description: '' } as Record<string, unknown>)
      invalidate('presets')
      open(p)
    } catch (e) { toast.error(e) }
  }

  if (editing) {
    return (
      <div className="page" style={{ maxWidth: 1320 }}>
        <header className="page-head">
          <div>
            <button className="btn btn-ghost btn-sm" style={{ marginLeft: -10, marginBottom: 8 }} onClick={() => {
              if (JSON.stringify(editing) !== original) setConfirmLeave(true)
              else setEditing(null)
            }}><ArrowLeft /> All presets</button>
            <h1 className="h1">{editing.name || 'Untitled preset'}</h1>
          </div>
        </header>
        <PresetEditor value={editing} onChange={setEditing} onSave={save} dirty={JSON.stringify(editing) !== original}
          onDuplicate={async () => {
            try {
              const copy = await api.post<Preset>(`/api/presets/${editing.id}/duplicate`)
              invalidate('presets')
              open(copy)
              toast.ok('Duplicated.')
            } catch (e) { toast.error(e) }
          }}
          onDelete={() => setConfirmDelete(true)} />
        {confirmLeave && (
          <Confirm title="Leave without saving?" body={`Your changes to “${editing.name}” will be lost.`} confirmLabel="Discard changes" danger
            onClose={() => setConfirmLeave(false)} onConfirm={() => setEditing(null)} />
        )}
        {confirmDelete && (
          <Confirm title="Delete this preset?" body={`“${editing.name}” will be removed. Prints already made keep their settings.`} confirmLabel="Delete preset" danger
            onClose={() => setConfirmDelete(false)}
            onConfirm={async () => {
              try { await api.del(`/api/presets/${editing.id}`); invalidate('presets'); setEditing(null) } catch (e) { toast.error(e) }
            }} />
        )}
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">Presets</h1>
          <p className="lede">Everything about how a print comes out: paper, size, borders, captions, color and quality. Schedules and one-off prints use these.</p>
        </div>
        <div className="actions"><button className="btn btn-paper" onClick={create}><Plus /> New preset</button></div>
      </header>
      {presets.isLoading ? <Loading /> : !presets.data?.length ? (
        <Empty icon={<SlidersHorizontal />} title="No presets yet" action={<button className="btn btn-paper" onClick={create}><Plus /> New preset</button>}>
          A preset remembers the paper, size, border and color settings for a kind of print.
        </Empty>
      ) : (
        <div className="preset-list">
          {presets.data.map((p, n) => {
            const size = sizes.data?.find((s) => s.keyword === p.output.media_size)
            const paper = papers.data?.find((x) => x.id === p.output.paper_id)
            return (
              <button key={p.id} className="preset-card" style={{ ['--i' as string]: n }} onClick={() => open(p)}>
                <span className="swatch"><PageSwatch preset={p} w={size?.width_mm ?? 101.6} h={size?.height_mm ?? 152.4} tint={paper?.tint} /></span>
                <span className="stack-s" style={{ minWidth: 0, gap: 4 }}>
                  <span className="h3">{p.name}</span>
                  <span className="small muted">{size?.label ?? p.size_label}, {p.paper_name}</span>
                  {p.description && <span className="small faint" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{p.description}</span>}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

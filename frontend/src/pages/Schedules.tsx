import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Album as AlbumIcon, CalendarHeart, Clock, Heart, Images, Plus, Printer, Search, Shuffle, Star, Tag, Trash2, UserRound, Sparkles,
} from 'lucide-react'
import { api, thumbUrl } from '../lib/api'
import { useAlbums, useInvalidate, usePeople, usePresets, useSchedules, useStatus } from '../lib/hooks'
import type { Schedule, SourceKind, SourceSpec } from '../lib/types'
import { fmtDateTime, photoTitle, plural, whenInline, whenLabel } from '../lib/format'
import { inkBurst } from '../lib/fx'
import { Confirm, Drawer, Empty, Field, Loading, NumberInput, Segmented, Select, Slider, Toggle, useToast } from '../components/ui'
import { INKS } from '../components/Ink'
import { PrintSheet } from '../components/PrintSheet'

const SOURCE_META: Record<SourceKind, { label: string; icon: typeof Heart; hint: string }> = {
  favorites: { label: 'Favorites', icon: Heart, hint: 'Photos you hearted in Immich' },
  on_this_day: { label: 'On this day', icon: CalendarHeart, hint: 'Taken around today’s date in past years' },
  memories: { label: 'Immich memories', icon: Sparkles, hint: 'Today’s memories from Immich' },
  album: { label: 'Album', icon: AlbumIcon, hint: 'One or more albums' },
  person: { label: 'People', icon: UserRound, hint: 'Photos of the people you choose' },
  rating: { label: 'Star rating', icon: Star, hint: 'Photos rated in Immich' },
  smart: { label: 'Smart search', icon: Search, hint: 'A plain-language description' },
  recent: { label: 'Recent', icon: Clock, hint: 'Taken in the last few weeks' },
  tag: { label: 'Tag', icon: Tag, hint: 'Photos with a tag' },
  random: { label: 'Whole library', icon: Shuffle, hint: 'Anything in your library' },
}
const SOURCE_ORDER: SourceKind[] = ['favorites', 'on_this_day', 'memories', 'album', 'person', 'rating', 'smart', 'recent', 'random']
const MIX_COLORS = [INKS[3].hex, INKS[5].hex, INKS[7].hex, INKS[4].hex, INKS[6].hex, INKS[8].hex, INKS[2].hex, '#b9b9b9']

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function newSource(kind: SourceKind): SourceSpec {
  return {
    id: Math.random().toString(16).slice(2, 14), kind, weight: 2, album_ids: [], person_ids: [], person_mode: 'any', tag_ids: [],
    query: '', min_rating: 4, recent_days: 30, window_days: 3, favorites_only: false, label: '',
  }
}

function blankSchedule(presetId: string): Schedule {
  return {
    id: '', name: 'New schedule', enabled: true, preset_id: presetId,
    timing: { frequency: 'weekly', time: '09:00', weekdays: [5], day_of_month: 1, every_n_days: 3, cron: '0 9 * * 6' },
    sources: [newSource('favorites')],
    filters: {
      include_archived: false, taken_after: null, taken_before: null, min_ppi: 180, orientation: 'any', exclude_screenshots: true,
      avoid_repeats_days: 365, exclude_album_ids: [], require_people: false, smart_pick: true, candidates: 8, skip_blurry: true,
    },
    approval: { mode: 'preview', lead_hours: 12 }, verify_paper: false, catch_up_hours: 6,
    notify: { on_pick: true, on_print: true, on_error: true }, next_run_at: null, last_run_at: null,
  }
}

function MultiPick({ items, selected, onChange, empty }: { items: { id: string; name: string; meta?: string }[]; selected: string[]; onChange: (ids: string[]) => void; empty: string }) {
  const [q, setQ] = useState('')
  const shown = items.filter((i) => i.name.toLowerCase().includes(q.toLowerCase()))
  if (!items.length) return <div className="small faint">{empty}</div>
  return (
    <div className="stack-s">
      {items.length > 8 && <input className="input" placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} />}
      <div className="multi-pick">
        {shown.map((i) => (
          <label key={i.id} className="row" style={{ padding: '5px 0', cursor: 'pointer' }}>
            <input type="checkbox" checked={selected.includes(i.id)}
              onChange={(e) => onChange(e.target.checked ? [...selected, i.id] : selected.filter((x) => x !== i.id))} />
            <span className="grow ellipsis">{i.name}</span>
            {i.meta && <span className="small faint">{i.meta}</span>}
          </label>
        ))}
      </div>
    </div>
  )
}

function SourceEditor({ src, onChange, onRemove, color, share }: { src: SourceSpec; onChange: (s: SourceSpec) => void; onRemove: () => void; color: string; share: number }) {
  const meta = SOURCE_META[src.kind]
  const albums = useAlbums(src.kind === 'album')
  const people = usePeople(src.kind === 'person')
  const Icon = meta.icon
  const set = (patch: Partial<SourceSpec>) => onChange({ ...src, ...patch })
  let config: ReactNode = null
  if (src.kind === 'album') {
    config = <MultiPick items={(albums.data ?? []).map((a) => ({ id: a.id, name: a.name, meta: String(a.count) }))}
      selected={src.album_ids} onChange={(ids) => set({ album_ids: ids })} empty={albums.isLoading ? 'Loading albums…' : 'No albums found.'} />
  } else if (src.kind === 'person') {
    config = (
      <div className="stack-s">
        <MultiPick items={(people.data ?? []).filter((p) => p.name).map((p) => ({ id: p.id, name: p.name }))}
          selected={src.person_ids} onChange={(ids) => set({ person_ids: ids })} empty={people.isLoading ? 'Loading people…' : 'Name people in Immich first.'} />
        {src.person_ids.length > 1 && (
          <Segmented value={src.person_mode} onChange={(v) => set({ person_mode: v })}
            options={[{ value: 'any', label: 'Any of them' }, { value: 'all', label: 'All together' }]} />
        )}
      </div>
    )
  } else if (src.kind === 'smart') {
    config = <input className="input" placeholder="e.g. sunset at the beach" value={src.query} onChange={(e) => set({ query: e.target.value })} />
  } else if (src.kind === 'rating') {
    config = <Segmented value={src.min_rating} onChange={(v) => set({ min_rating: v })}
      options={[3, 4, 5].map((n) => ({ value: n, label: `${n}★${n < 5 ? ' and up' : ''}` }))} />
  } else if (src.kind === 'recent') {
    config = <div className="row"><span className="small muted">Last</span><NumberInput value={src.recent_days} min={1} max={3650} onChange={(v) => set({ recent_days: v })} width={80} /><span className="small muted">days</span></div>
  } else if (src.kind === 'on_this_day') {
    config = <div className="row"><span className="small muted">Within</span><NumberInput value={src.window_days} min={0} max={30} onChange={(v) => set({ window_days: v })} width={70} /><span className="small muted">days of today’s date</span></div>
  }
  return (
    <div className="source-row">
      <span className="source-icon" style={{ boxShadow: `inset 3px 0 0 ${color}` }}><Icon /></span>
      <div className="stack-s" style={{ minWidth: 0 }}>
        <div>
          <div className="strong">{meta.label}</div>
          <div className="small faint">{meta.hint}</div>
        </div>
        {config}
        {!['favorites', 'random'].includes(src.kind) && (
          <Toggle checked={src.favorites_only} onChange={(v) => set({ favorites_only: v })} label={<span className="small">Favorites only</span>} />
        )}
      </div>
      <div className="weight">
        <Slider label={<span className="small">Chance</span>} value={src.weight} min={0} max={10} onChange={(v) => set({ weight: v })}
          format={() => `${Math.round(share * 100)}%`} track={color} />
      </div>
      <button className="btn btn-ghost btn-icon btn-sm" onClick={onRemove} aria-label={`Remove ${meta.label}`}><Trash2 /></button>
    </div>
  )
}

function TimingPreview({ timing }: { timing: Schedule['timing'] }) {
  const [res, setRes] = useState<{ text: string; runs: string[]; timezone: string } | null>(null)
  const key = JSON.stringify(timing)
  useEffect(() => {
    const t = setTimeout(() => {
      api.post<{ text: string; runs: string[]; timezone: string }>('/api/schedules/preview-times', { timing }).then(setRes).catch(() => setRes(null))
    }, 200)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  if (!res) return null
  return (
    <div className="small muted">
      {res.runs.length ? <>Next: {res.runs.slice(0, 3).map((r) => whenLabel(r)).join('; ')} <span className="faint">({res.timezone})</span></> : 'This timing never runs.'}
    </div>
  )
}

function ScheduleEditor({ initial, onClose }: { initial: Schedule; onClose: () => void }) {
  const [s, setS] = useState<Schedule>(structuredClone(initial))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const presets = usePresets()
  const albums = useAlbums()
  const toast = useToast()
  const invalidate = useInvalidate()
  const set = (fn: (x: Schedule) => void) => setS((cur) => { const n = structuredClone(cur); fn(n); return n })
  const totalWeight = s.sources.reduce((a, b) => a + b.weight, 0) || 1

  async function save() {
    try {
      if (s.id) await api.put(`/api/schedules/${s.id}`, s as unknown as Record<string, unknown>)
      else await api.post('/api/schedules', s as unknown as Record<string, unknown>)
      toast.ok(`Saved “${s.name}”.`)
      invalidate('schedules', 'dashboard')
      onClose()
    } catch (e) { toast.error(e) }
  }

  const t = s.timing
  return (
    <Drawer title={s.id ? 'Edit schedule' : 'New schedule'} onClose={onClose} footer={
      <>
        <div>{s.id && <button className="btn btn-ghost btn-danger" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete</button>}</div>
        <div className="btn-row">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-paper" onClick={save}>Save schedule</button>
        </div>
      </>
    }>
      <div className="stack" style={{ gap: 26 }}>
        <div className="grid-2">
          <Field label="Name"><input className="input" value={s.name} onChange={(e) => set((x) => { x.name = e.target.value })} /></Field>
          <Field label="Status"><Toggle checked={s.enabled} onChange={(v) => set((x) => { x.enabled = v })} label={s.enabled ? 'On' : 'Off'} /></Field>
        </div>

        <section className="stack">
          <h3 className="h3">When</h3>
          <Segmented value={t.frequency} onChange={(v) => set((x) => { x.timing.frequency = v })}
            options={[{ value: 'daily', label: 'Daily' }, { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' },
              { value: 'every_n_days', label: 'Every few days' }, { value: 'cron', label: 'Custom' }]} />
          <div className="row wrap" style={{ gap: 14, alignItems: 'flex-end' }}>
            {t.frequency !== 'cron' && (
              <Field label="Time"><input type="time" className="input" style={{ width: 130 }} value={t.time} onChange={(e) => set((x) => { x.timing.time = e.target.value || '08:00' })} /></Field>
            )}
            {t.frequency === 'weekly' && (
              <Field label="Days">
                <div className="seg">
                  {WEEKDAYS.map((d, i) => (
                    <button key={d} type="button" className={t.weekdays.includes(i) ? 'on' : ''} aria-pressed={t.weekdays.includes(i)}
                      onClick={() => set((x) => { x.timing.weekdays = x.timing.weekdays.includes(i) ? x.timing.weekdays.filter((w) => w !== i) : [...x.timing.weekdays, i].sort() })}>{d}</button>
                  ))}
                </div>
              </Field>
            )}
            {t.frequency === 'monthly' && (
              <Field label="Day of month"><NumberInput value={t.day_of_month} min={1} max={28} onChange={(v) => set((x) => { x.timing.day_of_month = v })} width={80} /></Field>
            )}
            {t.frequency === 'every_n_days' && (
              <Field label="Every"><NumberInput value={t.every_n_days} min={1} max={60} suffix="days" onChange={(v) => set((x) => { x.timing.every_n_days = v })} width={80} /></Field>
            )}
            {t.frequency === 'cron' && (
              <Field label="Cron expression" hint="Minute, hour, day, month, weekday — in the server’s time zone.">
                <input className="input" style={{ width: 220 }} value={t.cron} onChange={(e) => set((x) => { x.timing.cron = e.target.value })} />
              </Field>
            )}
          </div>
          <TimingPreview timing={t} />
        </section>

        <section className="stack">
          <h3 className="h3">How it prints</h3>
          <Field label="Preset" hint={<Link to="/presets">Edit presets</Link>}>
            <Select value={s.preset_id} onChange={(v) => set((x) => { x.preset_id = v })}
              options={(presets.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
          </Field>
        </section>

        <section className="stack">
          <div className="row-between">
            <h3 className="h3">Where photos come from</h3>
            <select className="select" style={{ width: 'auto' }} value="" aria-label="Add a source"
              onChange={(e) => { const k = e.target.value as SourceKind; if (k) set((x) => { x.sources.push(newSource(k)) }) }}>
              <option value="">Add a source…</option>
              {SOURCE_ORDER.map((k) => <option key={k} value={k}>{SOURCE_META[k].label}</option>)}
            </select>
          </div>
          {s.sources.length > 0 && (
            <div className="mix-bar" aria-hidden="true">
              {s.sources.map((src, i) => <i key={src.id} style={{ width: `${(src.weight / totalWeight) * 100}%`, background: MIX_COLORS[i % MIX_COLORS.length] }} />)}
            </div>
          )}
          <div>
            {s.sources.map((src, i) => (
              <SourceEditor key={src.id} src={src} color={MIX_COLORS[i % MIX_COLORS.length]} share={src.weight / totalWeight}
                onChange={(n) => set((x) => { x.sources[i] = n })} onRemove={() => set((x) => { x.sources.splice(i, 1) })} />
            ))}
            {!s.sources.length && <div className="small faint">Add at least one source. Favorites is a great start.</div>}
          </div>
        </section>

        <section className="stack">
          <h3 className="h3">Which photos qualify</h3>
          <Slider label="Minimum detail for the paper size" value={s.filters.min_ppi} min={0} max={300} step={10}
            format={(v) => (v ? `${v} ppi` : 'Any')} onChange={(v) => set((x) => { x.filters.min_ppi = v })}
            hint="Skips photos too small to print sharply at this size. 180 ppi is a good floor; 300 is lab quality." />
          <div className="grid-2">
            <Field label="Don’t repeat a photo for">
              <Select value={s.filters.avoid_repeats_days} onChange={(v) => set((x) => { x.filters.avoid_repeats_days = v })}
                options={[{ value: 0, label: 'Allow repeats' }, { value: 30, label: '30 days' }, { value: 90, label: '3 months' }, { value: 180, label: '6 months' },
                  { value: 365, label: 'A year' }, { value: -1, label: 'Ever' }]} />
            </Field>
            <Field label="Orientation">
              <Select value={s.filters.orientation} onChange={(v) => set((x) => { x.filters.orientation = v })}
                options={[{ value: 'any', label: 'Any' }, { value: 'landscape', label: 'Landscape only' }, { value: 'portrait', label: 'Portrait only' }]} />
            </Field>
            <Field label="Taken after"><input type="date" className="input" value={s.filters.taken_after ?? ''} onChange={(e) => set((x) => { x.filters.taken_after = e.target.value || null })} /></Field>
            <Field label="Taken before"><input type="date" className="input" value={s.filters.taken_before ?? ''} onChange={(e) => set((x) => { x.filters.taken_before = e.target.value || null })} /></Field>
          </div>
          <div className="stack-s">
            <Toggle checked={s.filters.smart_pick} onChange={(v) => set((x) => { x.filters.smart_pick = v })} label="Smart pick"
              hint={`Compares ${s.filters.candidates} candidates for sharpness, exposure, framing and resolution, then prints the best.`} />
            {s.filters.smart_pick && <Toggle checked={s.filters.skip_blurry} onChange={(v) => set((x) => { x.filters.skip_blurry = v })} label="Skip blurry photos" />}
            <Toggle checked={s.filters.exclude_screenshots} onChange={(v) => set((x) => { x.filters.exclude_screenshots = v })} label="Skip screenshots" />
            <Toggle checked={s.filters.require_people} onChange={(v) => set((x) => { x.filters.require_people = v })} label="Only photos with people in them" />
            <Toggle checked={s.filters.include_archived} onChange={(v) => set((x) => { x.filters.include_archived = v })} label="Include archived photos" />
          </div>
          <Field label="Never print from these albums">
            <MultiPick items={(albums.data ?? []).map((a) => ({ id: a.id, name: a.name, meta: String(a.count) }))}
              selected={s.filters.exclude_album_ids} onChange={(ids) => set((x) => { x.filters.exclude_album_ids = ids })} empty="No albums." />
          </Field>
        </section>

        <section className="stack">
          <h3 className="h3">Before it prints</h3>
          <Segmented value={s.approval.mode} onChange={(v) => set((x) => { x.approval.mode = v })} block
            options={[{ value: 'auto', label: 'Just print' }, { value: 'preview', label: 'Show me first' }, { value: 'manual', label: 'Ask me' }]} />
          <div className="small muted">
            {s.approval.mode === 'auto' && 'The photo is chosen at print time and printed right away.'}
            {s.approval.mode === 'preview' && `The photo is chosen ${s.approval.lead_hours} hours early so you can swap or skip it. It prints unless you skip it.`}
            {s.approval.mode === 'manual' && `The photo is chosen ${s.approval.lead_hours} hours early and only prints if you approve it.`}
          </div>
          {s.approval.mode !== 'auto' && (
            <Slider label="Choose the photo this early" value={s.approval.lead_hours} min={1} max={48} format={(v) => `${v} h`}
              onChange={(v) => set((x) => { x.approval.lead_hours = v })} />
          )}
          <Toggle checked={s.verify_paper} onChange={(v) => set((x) => { x.verify_paper = v })} label="Check the loaded paper first"
            hint="Holds the print and notifies you if the printer reports different paper than the preset uses." />
          <Field label="If Printmich was offline at print time" hint="Prints late if it comes back within this window; otherwise waits for the next one.">
            <Select value={s.catch_up_hours} onChange={(v) => set((x) => { x.catch_up_hours = v })}
              options={[{ value: 0, label: 'Always print late' }, { value: 2, label: '2 hours' }, { value: 6, label: '6 hours' }, { value: 24, label: '24 hours' }]} />
          </Field>
        </section>

        <section className="stack-s">
          <h3 className="h3">Notify me</h3>
          <Toggle checked={s.notify.on_pick} onChange={(v) => set((x) => { x.notify.on_pick = v })} label="When a photo is chosen" />
          <Toggle checked={s.notify.on_print} onChange={(v) => set((x) => { x.notify.on_print = v })} label="When it’s printed" />
          <Toggle checked={s.notify.on_error} onChange={(v) => set((x) => { x.notify.on_error = v })} label="When something goes wrong" />
          <div className="small faint">Notification services are set up in <Link to="/settings">Settings</Link>.</div>
        </section>
      </div>
      {confirmDelete && (
        <Confirm title="Delete this schedule?" body={`“${s.name}” stops printing. Your printed photos stay on the wall.`} confirmLabel="Delete schedule" danger
          onClose={() => setConfirmDelete(false)}
          onConfirm={async () => {
            try { await api.del(`/api/schedules/${s.id}`); invalidate('schedules', 'dashboard'); onClose() } catch (e) { toast.error(e) }
          }} />
      )}
    </Drawer>
  )
}

export function SchedulesPage() {
  const schedules = useSchedules()
  const presets = usePresets()
  const status = useStatus()
  const toast = useToast()
  const invalidate = useInvalidate()
  const [editing, setEditing] = useState<Schedule | null>(null)
  const list = schedules.data ?? []
  const firstPreset = useMemo(() => presets.data?.[0]?.id ?? '', [presets.data])

  async function toggle(s: Schedule, enabled: boolean) {
    try {
      await api.put(`/api/schedules/${s.id}`, { ...s, enabled } as unknown as Record<string, unknown>)
      invalidate('schedules', 'dashboard')
      toast.ok(enabled ? `“${s.name}” is on.` : `“${s.name}” is off.`)
    } catch (e) { toast.error(e) }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">Schedules</h1>
          <p className="lede">A photo of the day, a weekly favorite, a monthly best-of. Each schedule picks from your sources and prints with a preset.</p>
        </div>
        <div className="actions"><button className="btn btn-paper" onClick={() => setEditing(blankSchedule(firstPreset))}><Plus /> New schedule</button></div>
      </header>
      {status.data && !status.data.immich && <div style={{ marginBottom: 18 }}><Empty icon={<Images />} title="Connect Immich first" action={<Link to="/settings" className="btn">Open settings</Link>}>Schedules need Immich to choose photos.</Empty></div>}
      {schedules.isLoading ? <Loading /> : list.length === 0 ? (
        <Empty icon={<CalendarHeart />} title="No schedules yet" action={<button className="btn btn-paper" onClick={() => setEditing(blankSchedule(firstPreset))}><Plus /> New schedule</button>}>
          Start with a photo of the day from your favorites, then add more whenever you like.
        </Empty>
      ) : list.map((s, n) => {
        const pick = s.pick
        const img = pick ? thumbUrl(pick.asset_id) : s.last_print?.thumb ?? null
        return (
          <article key={s.id} className={`schedule-card${s.enabled ? '' : ' off'}`} style={{ ['--i' as string]: n }}>
            <div className="schedule-thumb">
              {img ? <PrintSheet src={img} aspect={1} /> : <div className="schedule-thumb-empty"><Images size={22} /></div>}
            </div>
            <div className="stack-s" style={{ minWidth: 0 }}>
              <div className="row" style={{ gap: 10 }}>
                <h2 className="h2 ellipsis">{s.name}</h2>
                <span className={`chip ${s.enabled ? 'chip-ok' : ''}`}>{s.enabled ? 'On' : 'Off'}</span>
              </div>
              <div className="small muted">{s.timing_text}, {s.preset_name ?? 'no preset'}</div>
              <div className="small">
                {s.enabled && s.next_run_at ? <>Next print {whenInline(s.next_run_at)}{pick ? <>: <span className="strong">{photoTitle(pick.asset)}</span>{pick.status === 'skipped' ? ' (skipped)' : ''}</> : ''}</> : <span className="faint">Not scheduled</span>}
              </div>
              <div className="small faint">
                {plural(s.print_count ?? 0, 'print')} so far{s.last_run_at ? `, last ran ${fmtDateTime(s.last_run_at)}` : ''}. Sources: {s.sources.map((x) => SOURCE_META[x.kind]?.label).join(', ') || 'none'}.
              </div>
            </div>
            <div className="btn-row">
              <Toggle checked={s.enabled} onChange={(v) => toggle(s, v)} />
              <button className="btn btn-sm" onClick={() => setEditing(s)}>Edit</button>
              <button className="btn btn-sm" title="Print a photo from this schedule now"
                onClick={async (e) => { inkBurst(e.currentTarget); try { await api.post(`/api/schedules/${s.id}/run`); toast.ok('Printing now.'); invalidate('schedules', 'dashboard') } catch (err) { toast.error(err) } }}>
                <Printer /> Print now
              </button>
            </div>
          </article>
        )
      })}
      {editing && <ScheduleEditor initial={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

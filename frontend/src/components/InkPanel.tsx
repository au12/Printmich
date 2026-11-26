import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Check, Droplet, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useInk, useInvalidate } from '../lib/hooks'
import type { InkEvent, InkSettings, InkState, InkTank } from '../lib/types'
import { fmtDate, parseDate, plural, relativeTime } from '../lib/format'
import { INKS } from './Ink'
import { inkBurst } from '../lib/fx'
import { Dialog, Field, Loading, NumberInput, Segmented, Toggle, useToast } from './ui'

const INK_COLOR = Object.fromEntries(INKS.map((i) => [i.key, i.color]))

function list(names: string[]) {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

function ml(v: number | null | undefined) {
  return v == null ? '–' : `${v < 10 ? v.toFixed(1) : Math.round(v)} ml`
}

function TankLine({ t, n, onSet }: { t: InkTank; n: number; onSet: () => void }) {
  const pct = t.percent ?? 0
  const since = !t.since ? 'Not tracked yet'
    : t.since_kind === 'refill' ? `Refilled ${relativeTime(t.since)}`
    : `Tracking since ${fmtDate(parseDate(t.since), { month: 'short', day: 'numeric' })}`
  return (
    <div className={`tank-line${t.ink.endsWith('BK') ? ' blk' : ''}`}>
      <span className="sw" style={{ background: INK_COLOR[t.ink] ?? t.color }} />
      <span className="row" style={{ gap: 8, minWidth: 0 }}>
        {t.name}
        {t.status === 'empty' && <span className="chip chip-err">Refill now</span>}
        {t.status === 'low' && <span className="chip chip-warn">Low</span>}
      </span>
      <span className="meter" aria-hidden="true"><i style={{ width: `${pct}%`, background: INK_COLOR[t.ink] ?? t.color, ['--i' as string]: n }} /></span>
      <button className="btn btn-ghost btn-sm pct num" onClick={onSet} title={`Set the ${t.name} level by hand`}>
        {t.percent == null ? '–' : `${Math.round(pct)}%`}
      </button>
      <span className="small muted num ml">{ml(t.level_ml)}</span>
      <span className="small faint meta" title={t.prints ? `${plural(t.prints, 'print')} since` : undefined}>{since}</span>
    </div>
  )
}

function RefillDialog({ state, onClose, onDone }: { state: InkState; onClose: () => void; onDone: (s: InkState) => void }) {
  const toast = useToast()
  const low = state.tanks.filter((t) => t.status === 'low' || t.status === 'empty').map((t) => t.ink)
  const [sel, setSel] = useState<string[]>(low)
  const [added, setAdded] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const toggle = (k: string) => setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]))
  const tanks = state.tanks
  async function submit() {
    setBusy(true)
    try {
      const amounts = Object.fromEntries(sel.filter((k) => added[k]).map((k) => [k, Number(added[k])]))
      const next = await api.post<InkState>('/api/ink/refill', { inks: sel, added_ml: amounts })
      toast.ok(`Logged ${plural(sel.length, 'refilled tank')}.`)
      onDone(next)
    } catch (e) { toast.error(e) } finally { setBusy(false) }
  }
  return (
    <Dialog title="Log a refill" onClose={onClose} footer={<>
      <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
      <button className="btn btn-paper" disabled={!sel.length || busy} onClick={(e) => { inkBurst(e.currentTarget, 10); submit() }}><Droplet /> Log refill</button>
    </>}>
      <div className="stack">
        <p className="small muted" style={{ margin: 0 }}>Choose the tanks you topped up. Printmich counts them as full again.</p>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          {tanks.map((t) => (
            <button key={t.ink} type="button" className={`chip-toggle${t.ink.endsWith('BK') ? ' blk' : ''}`} aria-pressed={sel.includes(t.ink)} onClick={() => toggle(t.ink)}>
              {sel.includes(t.ink) ? <Check size={14} /> : <span className="sw" style={{ background: INK_COLOR[t.ink] ?? t.color }} />}{t.name}
              {t.percent != null && <span className="faint num">{Math.round(t.percent)}%</span>}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSel(tanks.map((t) => t.ink))}>Select all</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSel([])}>Clear</button>
        </div>
        {sel.length > 0 && (
          <Field label="Ink added (optional)" hint="Read it off the syringe, or weigh the tank before and after (1 g is about 1 ml). The gray numbers are what Printmich expects; it compares and corrects itself from then on.">
            <div className="refill-amounts">
              {tanks.filter((t) => sel.includes(t.ink)).map((t) => (
                <label key={t.ink} className="stack-s">
                  <span className="small">{t.name}</span>
                  <div className="row" style={{ gap: 6 }}>
                    <input className="input num" inputMode="decimal" value={added[t.ink] ?? ''} style={{ width: 90 }}
                      placeholder={t.level_ml != null ? (t.capacity_ml - t.level_ml).toFixed(1) : ''}
                      onChange={(e) => setAdded((a) => ({ ...a, [t.ink]: e.target.value.replace(/[^0-9.]/g, '') }))} />
                    <span className="small faint">ml</span>
                  </div>
                </label>
              ))}
            </div>
          </Field>
        )}
      </div>
    </Dialog>
  )
}

function SetLevelDialog({ tank, onClose, onDone }: { tank: InkTank; onClose: () => void; onDone: (s: InkState) => void }) {
  const toast = useToast()
  const [pct, setPct] = useState(Math.round(tank.percent ?? 100))
  return (
    <Dialog title={`Set ${tank.name}`} onClose={onClose} footer={<>
      <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
      <button className="btn btn-paper" onClick={async () => {
        try { onDone(await api.post<InkState>('/api/ink/level', { ink: tank.ink, percent: pct })); toast.ok(`${tank.name} set to ${pct}%.`) } catch (e) { toast.error(e) }
      }}>Set level</button>
    </>}>
      <Field label="How full is it?" hint="For when you can see the level in the tank. This doesn't count as a refill.">
        <NumberInput value={pct} min={0} max={100} suffix="%" onChange={setPct} />
      </Field>
    </Dialog>
  )
}

type Group = { at: string; events: InkEvent[] }

function History({ events, capacity, onUndo }: { events: InkEvent[]; capacity: number; onUndo: (g: Group) => void }) {
  const groups = useMemo(() => {
    const out: Group[] = []
    for (const e of events) {
      const g = out.find((x) => x.at === e.at && x.events[0].kind === e.kind)
      if (g) g.events.push(e)
      else out.push({ at: e.at, events: [e] })
    }
    return out.slice(0, 12)
  }, [events])
  if (!groups.length) return null
  const name = (k: string) => INKS.find((i) => i.key === k)?.name ?? k
  return (
    <div className="panel panel-tight list">
      {groups.map((g) => {
        const refill = g.events[0].kind === 'refill'
        const all = g.events.length === INKS.length
        const what = refill
          ? `Refilled ${all ? 'every tank' : g.events.map((e) => name(e.ink)).join(', ')}`
          : g.events[0].note === 'Set by hand' ? `Set ${name(g.events[0].ink)} to ${Math.round(((g.events[0].level_ml ?? 0) / capacity) * 100)}%` : 'Started tracking'
        const measured = g.events.filter((e) => e.used_ml != null && e.used_est_ml != null)
        return (
          <div key={`${g.at}-${g.events[0].id}`} className="list-row">
            <span className="small faint num" style={{ minWidth: 92 }}>{fmtDate(parseDate(g.at), { month: 'short', day: 'numeric', year: 'numeric' })}</span>
            <span className="grow">
              {what}
              {measured.length > 0 && (
                <span className="small faint" style={{ display: 'block' }}>
                  {measured.map((e) => `${name(e.ink)} took ${e.added_ml?.toFixed(1)} ml (estimated ${e.used_est_ml?.toFixed(1)} ml)`).join('; ')}
                </span>
              )}
            </span>
            <button className="btn btn-ghost btn-icon btn-sm" title="Undo this entry" aria-label="Undo this entry" onClick={() => onUndo(g)}><Trash2 /></button>
          </div>
        )
      })}
    </div>
  )
}

/** Ink tracking on the Printer page: printer readings, or Printmich's estimate with a refill log. */
export function InkPanel() {
  const ink = useInk()
  const invalidate = useInvalidate()
  const toast = useToast()
  const [refill, setRefill] = useState(false)
  const [setting, setSetting] = useState<InkTank | null>(null)
  const location = useLocation()
  const ready = !!ink.data
  useEffect(() => {
    if (ready && location.hash === '#ink') document.getElementById('ink')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [ready, location.hash])
  if (ink.isLoading || !ink.data) return <Loading inline label="Reading the tanks" />
  const st = ink.data
  const s = st.settings
  const tracking = st.tanks.some((t) => t.level_ml != null)
  const readings = st.printer.some((m) => m.level >= 0)

  const refresh = (_next?: InkState) => invalidate('ink', 'printer', 'dashboard')
  async function saveSettings(patch: Partial<InkSettings>) {
    try {
      await api.put('/api/settings', { ink: { ...s, ...patch } })
      refresh()
    } catch (e) { toast.error(e) }
  }
  async function start(from: 'printer' | 'full') {
    try { refresh(await api.post<InkState>('/api/ink/start', { from })); toast.ok('Tracking ink from now on.') } catch (e) { toast.error(e) }
  }

  const tracked = st.tanks.filter((t) => t.percent != null)
  const lowest = [...tracked].sort((a, b) => (a.percent ?? 0) - (b.percent ?? 0))[0]
  const calibrated = st.tanks.filter((t) => t.calibrations > 0)
  const needs = tracked.filter((t) => t.status === 'low' || t.status === 'empty')

  return (
    <section className="section" id="ink">
      <div className="section-head">
        <h2 className="h2">Ink</h2>
        <Segmented ariaLabel="Where ink levels come from" value={s.levels} onChange={(v) => saveSettings({ levels: v })}
          options={[{ value: 'printer', label: 'Printer readings' }, { value: 'estimate', label: 'Printmich estimate' }]} />
      </div>

      {s.levels === 'printer' ? (
        <div className="panel stack">
          <p className="small muted" style={{ margin: 0, maxWidth: '68ch' }}>
            Refilling Canon tanks or using third-party ink? A tank's chip only counts the ink it shipped with, so the printer stops once for a refilled tank (support code 1699) and, after you hold its Stop button for 5 seconds, stops tracking that tank for good. Printmich can estimate each tank from the pages it prints instead and remind you before one runs dry.
          </p>
          <div><button className="btn" onClick={() => saveSettings({ levels: 'estimate' })}><Droplet /> Estimate ink instead</button></div>
        </div>
      ) : !tracking ? (
        <div className="panel stack">
          <h3 className="h3">Where are the tanks now?</h3>
          <p className="small muted" style={{ margin: 0, maxWidth: '68ch' }}>Printmich counts down from here, using the ink each print needs. Tanks the printer can't read start full, and you can correct any tank later.</p>
          <div className="btn-row">
            <button className="btn btn-paper" disabled={!readings} onClick={() => start('printer')}>Use the printer's readings</button>
            <button className="btn" onClick={() => start('full')}>All tanks are full</button>
          </div>
        </div>
      ) : (
        <div className="stack">
          <div className="panel stack">
            <div className="row-between">
              <div className="stack-s">
                <div style={{ color: needs.length ? (needs.some((t) => t.status === 'empty') ? 'var(--err)' : 'var(--warn)') : 'var(--text)' }}>
                  {needs.length ? `${list(needs.map((t) => t.name))} ${needs.length === 1 ? 'is' : 'are'} running low.` : `Every tank is above ${s.remind_below}%.`}
                </div>
                <div className="small faint">Estimated from the ink each print needed since a tank was last filled{lowest ? `; lowest is ${lowest.name} at about ${ml(lowest.level_ml)}` : ''}.</div>
              </div>
              <div className="btn-row">
                {s.remind_days > 0 && <button className="btn btn-sm" onClick={async () => refresh(await api.post<InkState>('/api/ink/checked'))}>I checked the ink</button>}
                <button className="btn btn-paper" onClick={() => setRefill(true)}><Droplet /> Log a refill</button>
              </div>
            </div>
            <div className="tank-list">
              {st.tanks.map((t, n) => <TankLine key={t.ink} t={t} n={n} onSet={() => setSetting(t)} />)}
            </div>
            <p className="small faint" style={{ margin: 0 }}>
              {calibrated.length
                ? `Corrected for your printer using ${plural(Math.max(...calibrated.map((t) => t.calibrations)), 'measured refill')}.`
                : 'Starts from Canon’s published yields. Enter how much ink each refill takes and the estimate corrects itself.'}
            </p>
          </div>

          <div className="panel stack">
            <div className="grid-2">
              <Field label="Remind me to refill below"><NumberInput width={110} value={s.remind_below} min={0} max={90} suffix="%" onChange={(v) => saveSettings({ remind_below: v })} /></Field>
              <Field label="Hold scheduled prints below" hint="They wait for a refill rather than run a tank dry. 0 turns this off."><NumberInput width={110} value={s.hold_below} min={0} max={50} suffix="%" onChange={(v) => saveSettings({ hold_below: v })} /></Field>
              <Field label="Also remind me to check the ink every" hint="0 turns this off."><NumberInput width={110} value={s.remind_days} min={0} max={365} suffix="days" onChange={(v) => saveSettings({ remind_days: v })} /></Field>
              <Field label="Tank size" hint="PFI-5100 tanks hold 14.4 ml."><NumberInput width={110} value={s.tank_ml} min={1} max={1000} step={0.1} suffix="ml" onChange={(v) => saveSettings({ tank_ml: v })} /></Field>
            </div>
            <Toggle checked={s.hide_printer_warnings} onChange={(v) => saveSettings({ hide_printer_warnings: v })}
              label="Ignore the tank chips' low-ink warnings" hint="They're always on once a tank has been refilled. An ink-out stop that needs the Stop button still shows." />
          </div>

          <History events={st.events} capacity={s.tank_ml} onUndo={async (g) => {
            try {
              let next: InkState | null = null
              for (const e of g.events) next = await api.del<InkState>(`/api/ink/events/${e.id}`)
              refresh(next ?? undefined)
              toast.ok('Removed.')
            } catch (e) { toast.error(e) }
          }} />
        </div>
      )}

      {refill && <RefillDialog state={st} onClose={() => setRefill(false)} onDone={(n) => { setRefill(false); refresh(n) }} />}
      {setting && <SetLevelDialog tank={setting} onClose={() => setSetting(null)} onDone={(n) => { setSetting(null); refresh(n) }} />}
    </section>
  )
}

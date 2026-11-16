import { useEffect, useState } from 'react'
import { Check, CircleHelp, KeyRound, Send, Upload, X } from 'lucide-react'
import { api } from '../lib/api'
import { useInvalidate, useSettings } from '../lib/hooks'
import type { ImmichCheck, Settings } from '../lib/types'
import { Field, Loading, Notice, NumberInput, Segmented, Spinner, Toggle, useToast } from '../components/ui'

function Perm({ p }: { p: { name: string; why: string; granted: boolean | null } }) {
  return (
    <div className="row" style={{ alignItems: 'flex-start', gap: 10, padding: '5px 0' }}>
      {p.granted === null ? <CircleHelp size={16} className="faint" /> : p.granted ? <Check size={16} style={{ color: 'var(--ok)' }} /> : <X size={16} style={{ color: 'var(--text-3)' }} />}
      <div><div className="small" style={{ fontWeight: 560 }}>{p.name}</div><div className="small faint">{p.why}</div></div>
    </div>
  )
}

function ImmichSection({ s }: { s: Settings }) {
  const toast = useToast()
  const invalidate = useInvalidate()
  const locked = (k: string) => s.env_locked.includes(k)
  const [url, setUrl] = useState(s.immich_url)
  const [key, setKey] = useState('')
  const [publicUrl, setPublicUrl] = useState(s.immich_public_url)
  const [check, setCheck] = useState<ImmichCheck | null>(null)
  const [busy, setBusy] = useState(false)

  async function test(save: boolean) {
    setBusy(true)
    try {
      const r = await api.post<ImmichCheck>('/api/immich/test', { url, api_key: key || undefined })
      setCheck(r)
      if (save) {
        await api.put('/api/settings', { immich_url: url, immich_public_url: publicUrl, ...(key ? { immich_api_key: key } : {}) })
        setKey('')
        invalidate('settings', 'status', 'dashboard', 'browse', 'albums', 'people')
        toast.ok(r.ok ? 'Immich connected.' : 'Saved, but Immich reported a problem.')
      }
    } catch (e) { toast.error(e); setCheck(null) } finally { setBusy(false) }
  }

  return (
    <section className="panel stack">
      <div className="row-between"><h2 className="h2">Immich</h2>{s.immich_api_key_set && <span className="chip chip-ok">Connected</span>}</div>
      <div className="grid-2">
        <Field label="Server address" hint="Usually http://your-server:2283" extra={locked('immich_url') && <span className="badge-env">Set by environment</span>}>
          <input className="input" value={url} disabled={locked('immich_url')} onChange={(e) => setUrl(e.target.value)} placeholder="http://10.0.10.5:2283" />
        </Field>
        <Field label="API key" extra={locked('immich_api_key') && <span className="badge-env">Set by environment</span>}
          hint={s.immich_api_key_set ? `Saved key ends in ${s.immich_api_key_hint}. Paste a new one to replace it.` : 'Create one in Immich under Account Settings, API Keys.'}>
          <input className="input" type="password" autoComplete="off" disabled={locked('immich_api_key')} value={key} onChange={(e) => setKey(e.target.value)} placeholder={s.immich_api_key_set ? '••••••••' : 'Paste API key'} />
        </Field>
      </div>
      <Field label="Address for links" hint="Optional. Where your browser reaches Immich, if different (e.g. https://photos.example.com). Used for “Open in Immich”.">
        <input className="input" value={publicUrl} disabled={locked('immich_public_url')} onChange={(e) => setPublicUrl(e.target.value)} placeholder="https://photos.example.com" />
      </Field>
      <div className="btn-row">
        <button className="btn btn-paper" onClick={() => test(true)} disabled={busy}>{busy ? <Spinner size={14} /> : <Check />} Save and test</button>
        <button className="btn" onClick={() => test(false)} disabled={busy}>Test only</button>
      </div>
      <Notice>
        <strong>A read-only key is enough.</strong> When creating the key, choose these permissions: <span className="num">asset.read, asset.view, asset.download, album.read, person.read, tag.read, memory.read, face.read</span>. Printmich never changes your library unless you turn on write-back below.
      </Notice>
      {check && (
        <div className="stack">
          {check.ok ? <Notice kind="ok"><strong>Connected to Immich {check.version}</strong>{check.key_name ? ` with the key “${check.key_name}”` : ''}{check.read_only ? '. The key is read-only.' : check.full_access ? '. This key has full access; a read-only key is safer.' : '.'}</Notice>
            : <Notice kind="err"><strong>Immich {check.version} answered, but searching failed.</strong> {check.error}</Notice>}
          <div className="grid-3">
            <div><div className="label">Needed</div>{check.permissions.required.map((p) => <Perm key={p.name} p={p} />)}</div>
            <div><div className="label">Recommended</div>{check.permissions.recommended.map((p) => <Perm key={p.name} p={p} />)}</div>
            <div><div className="label">Write-back (optional)</div>{check.permissions.writeback.map((p) => <Perm key={p.name} p={p} />)}</div>
          </div>
          {!check.album_search && <Notice kind="warn">This Immich version is older than 1.135, so album sources load whole albums. Updating Immich makes them faster.</Notice>}
        </div>
      )}
    </section>
  )
}

function NotificationsSection({ s, save }: { s: Settings; save: (p: Partial<Settings>) => Promise<void> }) {
  const toast = useToast()
  const [urls, setUrls] = useState(s.notifications.urls.join('\n'))
  const n = s.notifications
  return (
    <section className="panel stack">
      <h2 className="h2">Notifications</h2>
      <Field label="Where to send them" hint={<>One Apprise URL per line, e.g. <span className="num">ntfys://ntfy.sh/my-prints</span>, <span className="num">discord://…</span>, <span className="num">tgram://…</span>, <span className="num">hassio://…</span>. <a href="https://github.com/caronc/apprise/wiki" target="_blank" rel="noreferrer">Supported services</a>.</>}>
        <textarea className="textarea" spellCheck={false} value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="ntfys://ntfy.sh/printmich" />
      </Field>
      <div className="grid-2">
        <Toggle checked={n.on_pick} onChange={(v) => save({ notifications: { ...n, on_pick: v } })} label="Photo chosen for the next print" />
        <Toggle checked={n.on_print} onChange={(v) => save({ notifications: { ...n, on_print: v } })} label="Print finished" />
        <Toggle checked={n.on_error} onChange={(v) => save({ notifications: { ...n, on_error: v } })} label="Problems and paper checks" />
        <Toggle checked={n.attach_preview} onChange={(v) => save({ notifications: { ...n, attach_preview: v } })} label="Attach a preview image" />
      </div>
      <div className="btn-row">
        <button className="btn btn-paper" onClick={() => save({ notifications: { ...n, urls: urls.split('\n').map((x) => x.trim()).filter(Boolean) } })}>Save</button>
        <button className="btn" onClick={async () => {
          try { await api.post('/api/settings/test-notification', { urls: urls.split('\n').map((x) => x.trim()).filter(Boolean) }); toast.ok('Test notification sent.') } catch (e) { toast.error(e) }
        }}><Send /> Send a test</button>
      </div>
    </section>
  )
}

function SecuritySection({ s }: { s: Settings }) {
  const toast = useToast()
  const invalidate = useInvalidate()
  const [pw, setPw] = useState('')
  const [token, setToken] = useState<string | null>(null)
  const envPw = s.env_locked.includes('password')
  return (
    <section className="panel stack">
      <h2 className="h2">Security</h2>
      {envPw ? <Notice>The password is set by the <strong>PRINTMICH_PASSWORD</strong> environment variable.</Notice> : (
        <div className="row wrap" style={{ alignItems: 'flex-end' }}>
          <Field label={s.password_set ? 'Change password' : 'Password'} hint={s.password_set ? 'Leave empty and save to remove the password.' : 'Recommended if Printmich is reachable from outside your network.'}>
            <input className="input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
          <button className="btn" onClick={async () => {
            try { await api.post('/api/auth/password', { password: pw }); setPw(''); invalidate('settings', 'auth'); toast.ok(pw ? 'Password saved.' : 'Password removed.') } catch (e) { toast.error(e) }
          }}><KeyRound /> {pw || !s.password_set ? 'Save password' : 'Remove password'}</button>
        </div>
      )}
      <Field label="API token" hint="For automations like Home Assistant: send it as “Authorization: Bearer <token>”, e.g. POST /api/schedules/<id>/run.">
        {token ? <div className="notice ok"><Check /><div><div className="small">Copy it now — it won't be shown again.</div><div className="num" style={{ wordBreak: 'break-all', color: 'var(--text)' }}>{token}</div></div></div> : (
          <div className="btn-row">
            <button className="btn" onClick={async () => { try { setToken((await api.post<{ token: string }>('/api/auth/token')).token); invalidate('settings') } catch (e) { toast.error(e) } }}>{s.api_token_set ? 'Replace token' : 'Create token'}</button>
            {s.api_token_set && <button className="btn btn-ghost btn-danger" onClick={async () => { await api.del('/api/auth/token'); invalidate('settings'); toast.ok('Token revoked.') }}>Revoke</button>}
          </div>
        )}
      </Field>
    </section>
  )
}

export function SettingsPage() {
  const settings = useSettings()
  const invalidate = useInvalidate()
  const toast = useToast()
  const s = settings.data
  const [wallTitle, setWallTitle] = useState('')
  useEffect(() => { if (s) setWallTitle(s.wall_title) }, [s])
  if (!s) return <Loading />

  async function save(patch: Partial<Settings>) {
    try {
      await api.put('/api/settings', patch as Record<string, unknown>)
      invalidate('settings', 'status')
      toast.ok('Saved.')
    } catch (e) { toast.error(e) }
  }

  return (
    <div className="page" style={{ maxWidth: 980 }}>
      <header className="page-head">
        <div>
          <h1 className="h1">Settings</h1>
          <p className="lede">Times use the server's time zone, {s.timezone}. Change it with the TZ variable on the container.</p>
        </div>
      </header>
      <div className="stack" style={{ gap: 20 }}>
        <ImmichSection s={s} />
        <NotificationsSection s={s} save={save} />

        <section className="panel stack">
          <h2 className="h2">Write back to Immich</h2>
          <div className="small muted">Off by default so the API key can stay read-only. Each needs extra permissions on the key.</div>
          <div className="grid-2">
            <div className="stack-s">
              <Toggle checked={s.writeback.album_enabled} onChange={(v) => save({ writeback: { ...s.writeback, album_enabled: v } })} label="Add printed photos to an album" hint="Needs album.create and albumAsset.create." />
              {s.writeback.album_enabled && <input className="input" defaultValue={s.writeback.album_name} onBlur={(e) => save({ writeback: { ...s.writeback, album_name: e.target.value } })} />}
            </div>
            <div className="stack-s">
              <Toggle checked={s.writeback.tag_enabled} onChange={(v) => save({ writeback: { ...s.writeback, tag_enabled: v } })} label="Tag printed photos" hint="Needs tag.create and tag.asset." />
              {s.writeback.tag_enabled && <input className="input" defaultValue={s.writeback.tag_name} onBlur={(e) => save({ writeback: { ...s.writeback, tag_name: e.target.value } })} />}
            </div>
          </div>
        </section>

        <section className="panel stack">
          <h2 className="h2">Printing</h2>
          <div className="grid-2">
            <Field label="If the printer is unreachable, retry every"><NumberInput value={s.retry_minutes} min={1} max={120} suffix="min" onChange={(v) => save({ retry_minutes: v })} /></Field>
            <Field label="Give up after"><NumberInput value={s.retry_hours} min={0} max={72} suffix="hours" onChange={(v) => save({ retry_hours: v })} /></Field>
            <Field label="Currency symbol"><input className="input" defaultValue={s.cost.currency} onBlur={(e) => save({ cost: { ...s.cost, currency: e.target.value || '$' } })} /></Field>
            <Field label="Ink cost per ml" hint="Priced from each print's estimated ink. Paper prices are set per paper."><NumberInput value={s.cost.ink_per_ml} min={0} max={100} step={0.01} onChange={(v) => save({ cost: { ...s.cost, ink_per_ml: v } })} /></Field>
            {!s.cost.ink_per_ml && <Field label="Or ink cost per square inch" hint="A flat rate, used when cost per ml is 0."><NumberInput value={s.cost.ink_per_sq_in} min={0} max={5} step={0.005} onChange={(v) => save({ cost: { ...s.cost, ink_per_sq_in: v } })} /></Field>}
          </div>
        </section>

        <section className="panel stack">
          <h2 className="h2">Display</h2>
          <div className="grid-2">
            <Field label="Units"><Segmented value={s.units} onChange={(v) => save({ units: v })} options={[{ value: 'in', label: 'Inches' }, { value: 'mm', label: 'Millimeters' }]} /></Field>
            <Field label="Wall title"><input className="input" value={wallTitle} onChange={(e) => setWallTitle(e.target.value)} onBlur={() => wallTitle !== s.wall_title && save({ wall_title: wallTitle })} /></Field>
          </div>
        </section>

        <SecuritySection s={s} />

        <section className="panel stack">
          <h2 className="h2">Backup</h2>
          <div className="small muted">Presets, paper calibrations, schedules and settings (without secrets) as one JSON file.</div>
          <div className="btn-row">
            <a className="btn" href="/api/settings/export" download="printmich-settings.json">Export</a>
            <label className="btn"><Upload /> Import…
              <input type="file" accept="application/json" hidden onChange={async (e) => {
                const f = e.target.files?.[0]
                if (!f) return
                try {
                  const r = await api.post<{ imported: Record<string, number> }>('/api/settings/import', JSON.parse(await f.text()))
                  toast.ok(`Imported ${r.imported.presets} presets, ${r.imported.papers} papers, ${r.imported.schedules} schedules.`)
                  invalidate('presets', 'papers', 'schedules', 'settings')
                } catch (err) { toast.error(err) }
                e.target.value = ''
              }} />
            </label>
          </div>
        </section>

        <div className="small faint">Printmich is open source. <a href="https://github.com/au12/printmich" target="_blank" rel="noreferrer">github.com/au12/printmich</a></div>
      </div>
    </div>
  )
}

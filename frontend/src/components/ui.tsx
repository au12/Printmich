import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, ChevronDown, CircleAlert, CircleCheck, Info, X } from 'lucide-react'

/* ---------------------------------------------------------------- fields */

export function Field({ label, hint, children, extra }: { label?: ReactNode; hint?: ReactNode; children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="field">
      {(label || extra) && (
        <div className="row-between">
          {label && <label>{label}</label>}
          {extra}
        </div>
      )}
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; hint?: ReactNode; disabled?: boolean }) {
  return (
    <label className="toggle" style={disabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {(label || hint) && (
        <span className="toggle-text">
          {label && <span>{label}</span>}
          {hint && <span className="hint">{hint}</span>}
        </span>
      )}
    </label>
  )
}

export function Segmented<T extends string | number>({ value, options, onChange, block, ariaLabel }: {
  value: T
  options: { value: T; label: ReactNode; title?: string }[]
  onChange: (v: T) => void
  block?: boolean
  ariaLabel?: string
}) {
  return (
    <div className={`seg${block ? ' block' : ''}`} role="radiogroup" aria-label={ariaLabel}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} title={o.title}
          className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Slider({ label, value, min, max, step = 1, onChange, format, track, hint }: {
  label: ReactNode
  value: number
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
  format?: (v: number) => string
  track?: string
  hint?: ReactNode
}) {
  const id = useId()
  const fmt = format ?? ((v: number) => (v > 0 ? `+${v}` : String(v)))
  return (
    <div className="slider" style={track ? ({ '--track': track } as React.CSSProperties) : undefined}>
      <label className="label" htmlFor={id}>{label}</label>
      <output htmlFor={id} className="num" title="Double-click to reset" onDoubleClick={() => onChange(min < 0 ? 0 : min)}>
        {fmt(value)}
      </output>
      <input id={id} type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} onDoubleClick={() => onChange(min < 0 ? 0 : min)} />
      {hint && <div className="hint" style={{ gridColumn: '1 / -1' }}>{hint}</div>}
    </div>
  )
}

export function Select<T extends string | number>({ value, onChange, options, disabled, ariaLabel }: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string; disabled?: boolean }[]
  disabled?: boolean
  ariaLabel?: string
}) {
  return (
    <select className="select" value={String(value)} disabled={disabled} aria-label={ariaLabel}
      onChange={(e) => {
        const o = options.find((x) => String(x.value) === e.target.value)
        if (o) onChange(o.value)
      }}>
      {options.map((o) => (
        <option key={String(o.value)} value={String(o.value)} disabled={o.disabled}>{o.label}</option>
      ))}
    </select>
  )
}

export function NumberInput({ value, onChange, min, max, step = 1, suffix, width }: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  suffix?: string
  width?: number
}) {
  const [text, setText] = useState(String(value))
  useEffect(() => setText(String(value)), [value])
  const commit = () => {
    const n = Number(text)
    if (Number.isFinite(n)) {
      const clamped = Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n))
      onChange(clamped)
      setText(String(clamped))
    } else setText(String(value))
  }
  const input = (
    <input className="input num" inputMode="decimal" value={text} style={width ? { width } : undefined}
      onChange={(e) => setText(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'ArrowUp') { e.preventDefault(); onChange(Math.min(max ?? Infinity, value + step)) } if (e.key === 'ArrowDown') { e.preventDefault(); onChange(Math.max(min ?? -Infinity, value - step)) } }} />
  )
  if (!suffix) return input
  return <div className="input-group">{input}<span className="addon">{suffix}</span></div>
}

/* ---------------------------------------------------------------- disclosure group */

export function Group({ title, summary, defaultOpen, children, icon }: { title: ReactNode; summary?: ReactNode; defaultOpen?: boolean; children: ReactNode; icon?: ReactNode }) {
  const [open, setOpen] = useState(!!defaultOpen)
  return (
    <section className={`group${open ? ' open' : ''}`}>
      <button type="button" className="group-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {icon}
        <span className="h3">{title}</span>
        {!open && summary && <span className="sum ellipsis">{summary}</span>}
        <ChevronDown className="chev" />
      </button>
      {open && <div className="group-body">{children}</div>}
    </section>
  )
}

/* ---------------------------------------------------------------- overlays */

function useEscape(onClose: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
}

function useBodyLock() {
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])
}

export function Dialog({ title, onClose, children, footer, wide, labelledBy }: { title?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean; labelledBy?: string }) {
  useEscape(onClose)
  useBodyLock()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { ref.current?.focus() }, [])
  return createPortal(
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`dialog${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy} tabIndex={-1} ref={ref}>
        {title && (
          <div className="dialog-head">
            <h2 className="h2" id={labelledBy}>{title}</h2>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close"><X /></button>
          </div>
        )}
        {children}
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function Drawer({ title, onClose, children, footer }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEscape(onClose)
  useBodyLock()
  return createPortal(
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="drawer-head">
          <h2 className="h2">{title}</h2>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close"><X /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </aside>
    </>,
    document.body,
  )
}

export function Confirm({ title, body, confirmLabel, danger, onConfirm, onClose }: { title: string; body: ReactNode; confirmLabel: string; danger?: boolean; onConfirm: () => void; onClose: () => void }) {
  return (
    <Dialog title={title} onClose={onClose} footer={
      <>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className={`btn ${danger ? 'btn-danger' : 'btn-paper'}`} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</button>
      </>
    }>
      <div className="muted">{body}</div>
    </Dialog>
  )
}

/* ---------------------------------------------------------------- toasts */

type Toast = { id: number; kind: 'ok' | 'err' | 'info'; text: ReactNode }
const ToastCtx = createContext<(kind: Toast['kind'], text: ReactNode) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: ReactNode) => {
    const id = Date.now() + Math.random()
    setItems((x) => [...x, { id, kind, text }])
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === 'err' ? 7000 : 3800)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(
        <div className="toasts" aria-live="polite">
          {items.map((t) => (
            <div key={t.id} className={`toast ${t.kind}`}>
              {t.kind === 'ok' ? <CircleCheck /> : t.kind === 'err' ? <CircleAlert /> : <Info />}
              <div>{t.text}</div>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  )
}

export function useToast() {
  const push = useContext(ToastCtx)
  return {
    ok: (t: ReactNode) => push('ok', t),
    err: (t: ReactNode) => push('err', t instanceof Error ? t.message : t),
    info: (t: ReactNode) => push('info', t),
    error: (e: unknown) => push('err', e instanceof Error ? e.message : String(e)),
  }
}

/* ---------------------------------------------------------------- misc */

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'err' | 'ok'; children: ReactNode }) {
  const Icon = kind === 'warn' ? AlertTriangle : kind === 'err' ? CircleAlert : kind === 'ok' ? CircleCheck : Info
  return <div className={`notice ${kind}`}><Icon /><div>{children}</div></div>
}

export function Spinner({ size = 18 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label="Loading" />
}

export function Empty({ title, children, action }: { title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="h2">{title}</div>
      {children && <div className="prose">{children}</div>}
      {action}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return <div className="row muted" style={{ padding: 24 }}><Spinner /> {label}…</div>
}

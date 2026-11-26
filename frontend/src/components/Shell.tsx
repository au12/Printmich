import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  CalendarClock, ChevronRight, House, Images, LayoutGrid, Layers, Moon, Printer, Settings as SettingsIcon, SlidersHorizontal, Sun, Ellipsis,
} from 'lucide-react'
import { Logo } from './Logo'
import { MiniInk } from './Ink'
import { useDashboard, useStatus } from '../lib/hooks'
import { useTheme } from '../lib/theme'
import type { Dashboard } from '../lib/types'

const NAV = [
  { to: '/', label: 'Today', icon: House, end: true },
  { to: '/wall', label: 'Wall', icon: LayoutGrid },
  { to: '/library', label: 'Library', icon: Images },
  { to: '/schedules', label: 'Schedules', icon: CalendarClock },
]
const NAV2 = [
  { to: '/presets', label: 'Presets', icon: SlidersHorizontal, hint: 'Paper, size, borders and color for a print' },
  { to: '/papers', label: 'Papers', icon: Layers, hint: 'Canon papers and their calibrations' },
  { to: '/printer', label: 'Printer', icon: Printer, hint: 'Connection, ink and what it supports' },
  { to: '/settings', label: 'Settings', icon: SettingsIcon, hint: 'Immich, notifications and security' },
]

/** One line for the printer's state, shared by the sidebar card, the top bar and the Today page. */
export function printerState(d: Dashboard | undefined): { text: string; cls: string; busy: boolean } | null {
  const p = d?.printer
  if (!p) return null
  if (!p.configured) return { text: 'No printer yet', cls: '', busy: false }
  const busy = (d?.queue?.length ?? 0) > 0
  if (!p.online) return { text: 'Offline', cls: 'err', busy: false }
  if (busy) return { text: 'Printing', cls: 'busy', busy: true }
  if (p.state === 'stopped') return { text: 'Needs attention', cls: 'warn', busy: false }
  return { text: 'Ready', cls: 'ok', busy: false }
}

function PrinterCard() {
  const { data } = useDashboard()
  const st = printerState(data)
  if (!st) return null
  const p = data!.printer
  return (
    <NavLink to="/printer" className="status-card" aria-label={`Printer: ${st.text}`}>
      <span className="status-line"><span className={`dot ${st.cls}`} /> {st.text}</span>
      {p.configured && p.online && <MiniInk markers={p.markers ?? []} tanks={p.ink?.tracking ? p.ink.tanks : undefined} />}
    </NavLink>
  )
}

function PrinterPill() {
  const { data } = useDashboard()
  const st = printerState(data)
  if (!st) return null
  return <NavLink to="/printer" className="status-line small"><span className={`dot ${st.cls}`} /> {st.text}</NavLink>
}

function ThemeButton() {
  const { theme, toggle } = useTheme()
  return (
    <button className="btn btn-ghost btn-icon btn-sm theme-btn" onClick={toggle} aria-label="Switch light or dark mode" title="Switch light or dark mode">
      {theme === 'light' ? <Moon key="moon" /> : <Sun key="sun" />}
    </button>
  )
}

export function Shell() {
  const loc = useLocation()
  const { data: status } = useStatus()
  const { data: dash } = useDashboard()
  const busy = !!printerState(dash)?.busy
  const isWall = loc.pathname.startsWith('/wall')
  const moreActive = NAV2.some((n) => loc.pathname.startsWith(n.to)) || loc.pathname.startsWith('/more')
  const queued = dash?.queue?.length ?? 0
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="Printmich home">
          <Logo size={40} intro busy={busy} />
          <span className="brand-word">Printmich</span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <Icon /> {label}
              {to === '/' && queued > 0 && <span className="nav-badge" title={`${queued} in progress`}>{queued}</span>}
            </NavLink>
          ))}
          <div className="nav-sep" />
          {NAV2.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <Icon /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <PrinterCard />
          <div className="row-between">
            <span className="tiny faint">{status?.demo ? 'Demo mode' : status?.version ? `Version ${status.version}` : ''}</span>
            <ThemeButton />
          </div>
        </div>
      </aside>

      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="Printmich home">
          <Logo size={30} busy={busy} />
          <span className="brand-word">Printmich</span>
        </NavLink>
        <div className="row">
          <PrinterPill />
          <ThemeButton />
        </div>
      </header>

      <main className={`main${isWall ? ' full' : ''}`}>
        <div className="route" key={loc.pathname}>
          <Outlet />
        </div>
      </main>

      <nav className="tabbar" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
            <Icon /> <span>{label}</span>
          </NavLink>
        ))}
        <NavLink to="/more" className={`tab${moreActive ? ' active' : ''}`}>
          <Ellipsis /> <span>More</span>
        </NavLink>
      </nav>
    </div>
  )
}

export function MorePage() {
  const { data: status } = useStatus()
  return (
    <div className="page">
      <header className="page-head"><h1 className="h1">More</h1></header>
      <div className="list panel panel-tight">
        {NAV2.map(({ to, label, icon: Icon, hint }) => (
          <NavLink key={to} to={to} className="list-row" style={{ textDecoration: 'none' }}>
            <span className="source-icon"><Icon /></span>
            <span className="grow">
              <span className="strong" style={{ display: 'block' }}>{label}</span>
              <span className="small faint">{hint}</span>
            </span>
            <ChevronRight size={18} className="chev" />
          </NavLink>
        ))}
      </div>
      <p className="tiny faint" style={{ textAlign: 'center', marginTop: 22 }}>{status?.demo ? 'Demo mode' : status?.version ? `Printmich ${status.version}` : ''}</p>
    </div>
  )
}

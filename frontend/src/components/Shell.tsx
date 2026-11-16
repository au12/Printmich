import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  CalendarClock, House, Images, LayoutGrid, Layers, Moon, Printer, Settings as SettingsIcon, SlidersHorizontal, Sun, Ellipsis,
} from 'lucide-react'
import { InkMark } from './Ink'
import { useDashboard, useStatus } from '../lib/hooks'
import { useTheme } from '../lib/theme'

const NAV = [
  { to: '/', label: 'Today', icon: House, end: true },
  { to: '/wall', label: 'Wall', icon: LayoutGrid },
  { to: '/library', label: 'Library', icon: Images },
  { to: '/schedules', label: 'Schedules', icon: CalendarClock },
]
const NAV2 = [
  { to: '/presets', label: 'Presets', icon: SlidersHorizontal },
  { to: '/papers', label: 'Papers', icon: Layers },
  { to: '/printer', label: 'Printer', icon: Printer },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

function PrinterMini() {
  const { data } = useDashboard()
  const p = data?.printer
  if (!p) return null
  if (!p.configured) return <NavLink to="/printer" className="status-line small"><span className="dot" /> No printer yet</NavLink>
  const busy = (data?.queue?.length ?? 0) > 0
  const state = !p.online ? 'Offline' : busy ? 'Printing' : p.state === 'stopped' ? 'Needs attention' : 'Ready'
  const cls = !p.online ? 'err' : busy ? 'busy' : p.state === 'stopped' ? 'warn' : 'ok'
  return (
    <NavLink to="/printer" className="status-line small" style={{ textDecoration: 'none' }}>
      <span className={`dot ${cls}`} /> {state}
    </NavLink>
  )
}

export function Shell() {
  const loc = useLocation()
  const { data: status } = useStatus()
  const { theme, toggle } = useTheme()
  const isWall = loc.pathname.startsWith('/wall')
  const moreActive = NAV2.some((n) => loc.pathname.startsWith(n.to)) || loc.pathname.startsWith('/more')
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="Printmich home">
          <InkMark size={24} />
          <span className="brand-word">Printmich</span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <Icon /> {label}
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
          <PrinterMini />
          <div className="row-between">
            <span className="tiny faint">{status?.demo ? 'Demo mode' : status?.version ? `Version ${status.version}` : ''}</span>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={toggle} aria-label="Switch light or dark mode" title="Switch light or dark mode">
              {theme === 'light' ? <Moon /> : <Sun />}
            </button>
          </div>
        </div>
      </aside>

      <header className="topbar">
        <NavLink to="/" className="brand" style={{ padding: 0 }} aria-label="Printmich home">
          <InkMark size={20} />
          <span className="brand-word" style={{ fontSize: 17 }}>Printmich</span>
        </NavLink>
        <div className="row">
          <PrinterMini />
          <button className="btn btn-ghost btn-icon btn-sm" onClick={toggle} aria-label="Switch light or dark mode">
            {theme === 'light' ? <Moon /> : <Sun />}
          </button>
        </div>
      </header>

      <main className={`main${isWall ? ' full' : ''}`}>
        <Outlet />
      </main>

      <nav className="tabbar" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
            <Icon /> {label}
          </NavLink>
        ))}
        <NavLink to="/more" className={`tab${moreActive ? ' active' : ''}`}>
          <Ellipsis /> More
        </NavLink>
      </nav>
    </div>
  )
}

export function MorePage() {
  return (
    <div className="page">
      <header className="page-head"><h1 className="h1">More</h1></header>
      <div className="list panel" style={{ padding: '4px 18px' }}>
        {NAV2.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className="list-row" style={{ textDecoration: 'none' }}>
            <Icon size={18} /> <span className="grow">{label}</span>
          </NavLink>
        ))}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { api, ApiError } from './lib/api'
import { MorePage, Shell } from './components/Shell'
import { ToastProvider, Loading } from './components/ui'
import { Logo } from './components/Logo'
import { TodayPage } from './pages/Today'
import { WallPage } from './pages/Wall'
import { LibraryPage } from './pages/Library'
import { SchedulesPage } from './pages/Schedules'
import { PresetsPage } from './pages/Presets'
import { PapersPage } from './pages/Papers'
import { PrinterPage } from './pages/Printer'
import { SettingsPage } from './pages/Settings'

const client = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => !(err instanceof ApiError && [400, 401, 403, 404, 422].includes(err.status)) && count < 2,
      refetchOnWindowFocus: true,
      staleTime: 5_000,
    },
  },
})

function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="login">
      <form className="login-card" onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await api.post('/api/auth/login', { password })
          onDone()
        } catch (err) {
          setError((err as Error).message)
        } finally {
          setBusy(false)
        }
      }}>
        <div className="row" style={{ gap: 14 }}>
          <Logo size={52} intro />
          <div>
            <div className="brand-word" style={{ fontSize: 26 }}>Printmich</div>
            <div className="small muted" style={{ marginTop: 6 }}>Photos from Immich, on paper.</div>
          </div>
        </div>
        <div className="field">
          <label htmlFor="pw">Password</label>
          <input id="pw" className="input" type="password" autoFocus autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
          {error && <div className="small" role="alert" style={{ color: 'var(--err)' }}>{error}</div>}
        </div>
        <button className="btn btn-paper btn-lg" disabled={busy || !password}>{busy ? 'Logging in…' : 'Log in'}</button>
      </form>
    </div>
  )
}

function Gate() {
  const qc = useQueryClient()
  const auth = useQuery({ queryKey: ['auth'], queryFn: () => api.get<{ enabled: boolean; authenticated: boolean }>('/api/auth/status') })
  useEffect(() => {
    const h = () => qc.invalidateQueries({ queryKey: ['auth'] })
    window.addEventListener('printmich:unauthorized', h)
    return () => window.removeEventListener('printmich:unauthorized', h)
  }, [qc])
  if (auth.isLoading) return <div className="boot"><div className="stack"><Logo size={84} intro wave /><Loading label="Warming up the printer" /></div></div>
  if (auth.data?.enabled && !auth.data.authenticated) {
    return <Login onDone={() => { qc.invalidateQueries() }} />
  }
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<TodayPage />} />
        <Route path="wall" element={<WallPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="schedules" element={<SchedulesPage />} />
        <Route path="presets" element={<PresetsPage />} />
        <Route path="papers" element={<PapersPage />} />
        <Route path="printer" element={<PrinterPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="more" element={<MorePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export function App() {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <BrowserRouter>
          <Gate />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}

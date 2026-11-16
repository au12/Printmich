import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, postImage } from './api'
import type {
  Album, AppStatus, AssetSummary, Dashboard, EventItem, Paper, Person, Preset, PrinterInfo, PrintItem, RenderInfo,
  Schedule, Settings, Stats,
} from './types'

export const useStatus = () => useQuery({ queryKey: ['status'], queryFn: () => api.get<AppStatus>('/api/status') })
export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: () => api.get<Settings>('/api/settings') })
export const useDashboard = () =>
  useQuery({ queryKey: ['dashboard'], queryFn: () => api.get<Dashboard>('/api/dashboard'), refetchInterval: 6000 })
export const usePresets = () => useQuery({ queryKey: ['presets'], queryFn: () => api.get<Preset[]>('/api/presets') })
export const usePapers = () => useQuery({ queryKey: ['papers'], queryFn: () => api.get<Paper[]>('/api/papers') })
export const useSchedules = () =>
  useQuery({ queryKey: ['schedules'], queryFn: () => api.get<Schedule[]>('/api/schedules'), refetchInterval: 15000 })
export const usePrinter = () =>
  useQuery({ queryKey: ['printer'], queryFn: () => api.get<PrinterInfo>('/api/printer'), refetchInterval: 15000 })
export const useStats = () => useQuery({ queryKey: ['stats'], queryFn: () => api.get<Stats>('/api/stats') })
export const useEvents = (limit = 60) =>
  useQuery({ queryKey: ['events', limit], queryFn: () => api.get<EventItem[]>(`/api/events?limit=${limit}`), refetchInterval: 10000 })
export const useSizes = () =>
  useQuery({
    queryKey: ['sizes'],
    queryFn: () => api.get<{ keyword: string; label: string; width_mm: number; height_mm: number; borderless: boolean }[]>('/api/sizes'),
    staleTime: 600_000,
  })

export const useAlbums = (enabled = true) =>
  useQuery({ queryKey: ['albums'], queryFn: () => api.get<Album[]>('/api/immich/albums'), enabled, staleTime: 120_000 })
export const usePeople = (enabled = true) =>
  useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/api/immich/people'), enabled, staleTime: 120_000 })

export function usePrints(params: Record<string, string | number | boolean | undefined> = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)) })
  return useInfiniteQuery({
    queryKey: ['prints', params],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => api.get<{ items: PrintItem[]; total: number }>(`/api/prints?limit=60&offset=${pageParam}&${qs}`),
    getNextPageParam: (last, all) => {
      const n = all.reduce((s, p) => s + p.items.length, 0)
      return n < last.total ? n : undefined
    },
  })
}

export function useBrowse(source: string, extra: Record<string, string | undefined> = {}, enabled = true) {
  const qs = new URLSearchParams({ source })
  Object.entries(extra).forEach(([k, v]) => { if (v) qs.set(k, v) })
  return useInfiniteQuery({
    queryKey: ['browse', source, extra],
    initialPageParam: 1,
    enabled,
    queryFn: ({ pageParam }) => api.get<{ items: AssetSummary[]; next_page: number | null }>(`/api/immich/browse?${qs}&page=${pageParam}`),
    getNextPageParam: (last) => (source === 'random' ? undefined : last.next_page ?? undefined),
    staleTime: 60_000,
  })
}

/** Live print preview rendered by the server with the exact print pipeline. */
export function useRenderPreview(body: Record<string, unknown> | null, deps: unknown[] = [], delay = 220) {
  const [state, setState] = useState<{ url: string | null; info: RenderInfo | null; loading: boolean; error: string | null }>({
    url: null, info: null, loading: false, error: null,
  })
  const key = JSON.stringify(body)
  useEffect(() => {
    if (!body) return
    const ctrl = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    const t = setTimeout(() => {
      postImage('/api/render/preview', body as Record<string, unknown>, ctrl.signal)
        .then(({ url, info }) => setState((s) => {
          if (s.url) URL.revokeObjectURL(s.url)
          return { url, info, loading: false, error: null }
        }))
        .catch((e: unknown) => {
          if ((e as Error).name === 'AbortError') return
          setState((s) => ({ ...s, loading: false, error: (e as Error).message }))
        })
    }, delay)
    return () => { clearTimeout(t); ctrl.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ...deps])
  return state
}

export function useInvalidate() {
  const qc = useQueryClient()
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
}

export function useAction<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  return useMutation({ mutationFn: fn })
}

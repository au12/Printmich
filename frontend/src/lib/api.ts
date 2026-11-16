import type { RenderInfo } from './types'

export class ApiError extends Error {
  status: number
  kind?: string
  constructor(message: string, status: number, kind?: string) {
    super(message)
    this.status = status
    this.kind = kind
  }
}

type Json = Record<string, unknown> | unknown[] | null

async function request<T>(method: string, url: string, body?: Json | FormData): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin', headers: {} }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    ;(init.headers as Record<string, string>)['Content-Type'] = 'application/json'
  }
  const res = await fetch(url, init)
  if (res.status === 401 && !url.startsWith('/api/auth')) {
    window.dispatchEvent(new CustomEvent('printmich:unauthorized'))
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    let kind: string | undefined
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join('; ')
      kind = data.kind
    } catch {
      /* not json */
    }
    throw new ApiError(detail, res.status, kind)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: Json | FormData) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: Json) => request<T>('PUT', url, body),
  patch: <T>(url: string, body: Json) => request<T>('PATCH', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
}

/** POST that returns an image plus JSON metadata in the X-Printmich-Info header. */
export async function postImage(url: string, body: Json, signal?: AbortSignal): Promise<{ url: string; info: RenderInfo }> {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    let detail = `${res.status}`
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status)
  }
  const info = JSON.parse(decodeURIComponent(res.headers.get('X-Printmich-Info') || '%7B%7D')) as RenderInfo
  const blob = await res.blob()
  return { url: URL.createObjectURL(blob), info }
}

export const thumbUrl = (assetId: string, size: 'thumbnail' | 'preview' = 'thumbnail') =>
  `/api/immich/assets/${assetId}/thumbnail?size=${size}`
export const personThumbUrl = (personId: string) => `/api/immich/people/${personId}/thumbnail`
export const immichLink = (assetId: string) => `/api/immich/link/${assetId}`

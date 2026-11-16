import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Heart, Printer, Search } from 'lucide-react'
import { personThumbUrl, thumbUrl } from '../lib/api'
import { useAlbums, useBrowse, usePeople, useStatus } from '../lib/hooks'
import type { AssetSummary } from '../lib/types'
import { fmtDate, parseDate, plural } from '../lib/format'
import { PrintDialog } from '../components/PrintDialog'
import { Empty, Loading, Spinner } from '../components/ui'

const TABS = [
  { key: 'favorites', label: 'Favorites' },
  { key: 'recent', label: 'Recent' },
  { key: 'on_this_day', label: 'On this day' },
  { key: 'albums', label: 'Albums' },
  { key: 'people', label: 'People' },
  { key: 'search', label: 'Search' },
] as const
type TabKey = (typeof TABS)[number]['key']

function AssetGrid({ source, extra, onPick, empty }: { source: string; extra?: Record<string, string | undefined>; onPick: (a: AssetSummary) => void; empty: string }) {
  const q = useBrowse(source, extra ?? {}, source !== 'search' || !!extra?.q)
  const items = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data])
  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting && q.hasNextPage && !q.isFetchingNextPage) q.fetchNextPage() }, { rootMargin: '600px' })
    io.observe(el)
    return () => io.disconnect()
  }, [q])
  if (q.isLoading) return <Loading label="Loading photos" />
  if (q.error) return <Empty title="Couldn't load photos from Immich">{(q.error as Error).message}</Empty>
  if (!items.length) return <div className="muted" style={{ padding: '20px 0' }}>{empty}</div>
  return (
    <>
      <div className="asset-grid">
        {items.map((a) => (
          <button key={a.id} className="asset" onClick={() => onPick(a)} title={a.filename}>
            <img src={thumbUrl(a.id)} alt={a.description || a.filename} loading="lazy" decoding="async" />
            <span className="badge">
              {a.printed && <span title="Printed before"><Printer /></span>}
              {a.favorite && <span title="Favorite"><Heart fill="currentColor" /></span>}
            </span>
          </button>
        ))}
      </div>
      <div ref={sentinel} style={{ height: 1 }} />
      {q.isFetchingNextPage && <div className="row" style={{ justifyContent: 'center', padding: 18 }}><Spinner /></div>}
    </>
  )
}

export function LibraryPage() {
  const status = useStatus()
  const [tab, setTab] = useState<TabKey>('favorites')
  const [album, setAlbum] = useState<{ id: string; name: string } | null>(null)
  const [person, setPerson] = useState<{ id: string; name: string } | null>(null)
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [picked, setPicked] = useState<AssetSummary | null>(null)
  const albums = useAlbums(tab === 'albums')
  const people = usePeople(tab === 'people')

  if (status.data && !status.data.immich) {
    return (
      <div className="page">
        <header className="page-head"><h1 className="h1">Library</h1></header>
        <Empty title="Connect Immich to browse your photos" action={<Link to="/settings" className="btn btn-paper">Open settings</Link>}>
          Printmich needs your Immich server address and a read-only API key.
        </Empty>
      </div>
    )
  }

  const today = new Date()
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">Library</h1>
          <p className="lede">Pick any photo from Immich and print it now.</p>
        </div>
      </header>
      <div className="lib-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`btn btn-sm ${tab === t.key ? 'btn-paper' : ''}`}
            onClick={() => { setTab(t.key); setAlbum(null); setPerson(null) }}>{t.label}</button>
        ))}
      </div>

      {tab === 'favorites' && <AssetGrid source="favorites" onPick={setPicked} empty="No favorites yet. Heart photos in Immich and they show up here." />}
      {tab === 'recent' && <AssetGrid source="recent" onPick={setPicked} empty="No photos found." />}
      {tab === 'on_this_day' && (
        <>
          <p className="muted small" style={{ marginTop: -6 }}>Photos taken within three days of {fmtDate(today, { month: 'long', day: 'numeric' })} in past years.</p>
          <AssetGrid source="on_this_day" onPick={setPicked} empty="Nothing from this week in past years." />
        </>
      )}
      {tab === 'albums' && (album ? (
        <>
          <button className="btn btn-ghost btn-sm" onClick={() => setAlbum(null)} style={{ marginBottom: 12 }}><ArrowLeft /> All albums</button>
          <h2 className="h2" style={{ marginBottom: 14 }}>{album.name}</h2>
          <AssetGrid source="album" extra={{ id: album.id }} onPick={setPicked} empty="This album has no photos." />
        </>
      ) : albums.isLoading ? <Loading /> : albums.error ? <Empty title="Couldn't load albums">{(albums.error as Error).message}</Empty> : (
        <div className="collection-grid">
          {(albums.data ?? []).map((a) => (
            <button key={a.id} className="collection" onClick={() => setAlbum({ id: a.id, name: a.name })}>
              <div className="cover">{a.thumbnail && <img src={thumbUrl(a.thumbnail)} alt="" loading="lazy" />}</div>
              <div>
                <div style={{ fontWeight: 560 }}>{a.name}</div>
                <div className="small faint">{plural(a.count, 'photo')}{a.end ? `, ${parseDate(a.end)?.getFullYear()}` : ''}</div>
              </div>
            </button>
          ))}
          {!albums.data?.length && <div className="muted">No albums yet.</div>}
        </div>
      ))}
      {tab === 'people' && (person ? (
        <>
          <button className="btn btn-ghost btn-sm" onClick={() => setPerson(null)} style={{ marginBottom: 12 }}><ArrowLeft /> Everyone</button>
          <h2 className="h2" style={{ marginBottom: 14 }}>{person.name || 'Unnamed'}</h2>
          <AssetGrid source="person" extra={{ id: person.id }} onPick={setPicked} empty="No photos." />
        </>
      ) : people.isLoading ? <Loading /> : people.error ? <Empty title="Couldn't load people">{(people.error as Error).message}</Empty> : (
        <div className="row wrap" style={{ gap: 10 }}>
          {(people.data ?? []).filter((p) => p.name).map((p) => (
            <button key={p.id} className="person" onClick={() => setPerson({ id: p.id, name: p.name })}>
              <img src={personThumbUrl(p.id)} alt="" loading="lazy" />
              <span className="small">{p.name}</span>
            </button>
          ))}
          {!people.data?.some((p) => p.name) && <div className="muted">Name people in Immich to use them here.</div>}
        </div>
      ))}
      {tab === 'search' && (
        <>
          <form className="row" style={{ marginBottom: 18, maxWidth: 560 }} onSubmit={(e) => { e.preventDefault(); setSubmitted(query.trim()) }}>
            <input className="input" placeholder="Describe a photo, like “sunset over the lake” or “dog in the snow”" value={query}
              onChange={(e) => setQuery(e.target.value)} aria-label="Smart search" />
            <button className="btn btn-paper"><Search /> Search</button>
          </form>
          {submitted ? <AssetGrid source="search" extra={{ q: submitted }} onPick={setPicked} empty="No matches." />
            : <p className="muted small">Uses Immich's smart search, so plain descriptions work.</p>}
        </>
      )}
      {picked && <PrintDialog asset={picked} onClose={() => setPicked(null)} />}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getTracker, type TrackerRow } from '../api'
import { useApp } from '../AppContext'
import { daysSince, statusBadge } from '../format'
import { EmptyState, ErrorNote, PageLoading } from '../components/ui'

const COLUMNS: { key: string; label: string }[] = [
  { key: 'shortlisted', label: 'Shortlisted' },
  { key: 'generating', label: 'Generating' },
  { key: 'script_ready', label: 'Script ready' },
  { key: 'in_edit', label: 'In edit' },
  { key: 'approved', label: 'Approved' },
  { key: 'in_production', label: 'In production' },
  { key: 'shipped', label: 'Shipped' },
]
const HIDDEN = new Set(['dismissed', 'dropped'])

export default function Pipeline() {
  const { userName } = useApp()
  const [rows, setRows] = useState<TrackerRow[] | null>(null)
  const [error, setError] = useState('')
  const [mine, setMine] = useState(false)

  const load = useCallback(() => {
    getTracker()
      .then((r) => setRows(r.rows))
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    const t = window.setInterval(load, 10_000)
    return () => window.clearInterval(t)
  }, [load])

  if (error) return <ErrorNote message={error} />
  if (!rows) return <PageLoading label="Loading the board…" />

  const visible = rows.filter(
    (r) => !HIDDEN.has(r.status) && (!mine || r.claimed_by === userName),
  )
  const hiddenCount = rows.filter((r) => HIDDEN.has(r.status)).length

  return (
    <div className="fade-in-up">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white">Production pipeline</h1>
          <p className="text-sm text-zinc-500">{visible.length} ads in flight</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
            className="accent-violet-500"
          />
          My queue
        </label>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon="🎬"
          title="Nothing in the pipeline yet"
          hint="Shortlist a winning ad from the Library and generate a script to see it here."
        />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {COLUMNS.map((col) => {
            const items = visible.filter((r) => r.status === col.key)
            return (
              <div key={col.key} className="w-64 shrink-0">
                <div className="mb-2 flex items-center justify-between px-1">
                  <span className="text-sm font-medium text-zinc-300">{col.label}</span>
                  <span className="text-xs text-zinc-600">{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((r) => (
                    <Card key={`${r.competitor}-${r.ad_id}`} row={r} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {hiddenCount > 0 && (
        <p className="mt-4 text-xs text-zinc-600">
          {hiddenCount} ad{hiddenCount > 1 ? 's' : ''} dismissed or dropped (hidden).
        </p>
      )}
    </div>
  )
}

function Card({ row }: { row: TrackerRow }) {
  const b = statusBadge(row.status)
  const days = daysSince(row.updated_at)
  return (
    <Link
      to={`/ad/${row.pipeline}/${row.competitor}/${row.ad_id}`}
      className="block overflow-hidden rounded-xl border border-white/10 bg-zinc-900/70 transition-colors hover:border-violet-400/40"
    >
      <div className="flex gap-2.5 p-2.5">
        <div className="h-16 w-12 shrink-0 overflow-hidden rounded-md bg-zinc-800">
          {row.ad?.media_url && (
            <video src={row.ad.media_url} muted className="h-full w-full object-cover" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-zinc-200">
            {row.ad?.page_name || row.competitor}
          </div>
          <div className={`mt-1 inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${b.className}`}>
            {b.label}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-[10px] text-zinc-600">
            {row.claimed_by && <span className="text-zinc-400">{row.claimed_by}</span>}
            {days != null && <span>· {days}d in stage</span>}
          </div>
          <div className="mt-1 flex gap-1.5 text-[11px]">
            {row.rewrite_gdoc_url && (
              <span title="Script doc" className="text-emerald-400">📝</span>
            )}
            {row.verdict_at_shortlist && row.ad && row.ad.verdict !== row.verdict_at_shortlist && (
              <span title="Verdict changed since shortlisting" className="text-amber-400">⚠︎</span>
            )}
          </div>
        </div>
      </div>
    </Link>
  )
}

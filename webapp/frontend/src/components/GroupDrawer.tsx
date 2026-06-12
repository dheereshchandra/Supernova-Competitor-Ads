import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getGroup, type GroupDetail } from '../api'
import { posterUrl, runDaysLabel } from '../format'
import { ErrorNote, Spinner, StatusChip, VerdictBadge } from './ui'

/**
 * Right-side panel listing every ad that runs the same script — unfiltered,
 * so the team sees all language/visual variants even when the grid is narrowed.
 * Render with key={gid} — a gid change remounts, resetting the loading state.
 */
export default function GroupDrawer({
  pipeline,
  competitor,
  gid,
  onClose,
}: {
  pipeline: string
  competitor: string
  gid: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<GroupDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    getGroup(pipeline, competitor, gid)
      .then((d) => !cancelled && setDetail(d))
      .catch((e: Error) => !cancelled && setError(e.message || 'Could not load the group'))
    return () => {
      cancelled = true
    }
  }, [pipeline, competitor, gid])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const live = detail?.members.filter((m) => !m.is_retired).length ?? 0

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-white/10 bg-zinc-950 shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 p-5">
          <div>
            <h2 className="text-base font-semibold text-white">
              {detail
                ? `${detail.group_size_total} variants of this script`
                : 'Script variants'}
            </h2>
            {detail && (
              <p className="mt-0.5 text-xs text-zinc-500">
                {detail.languages_total} language{detail.languages_total === 1 ? '' : 's'} ·{' '}
                {live} live · {detail.winners_total} winner{detail.winners_total === 1 ? '' : 's'}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-zinc-500 hover:bg-white/5 hover:text-zinc-200"
            title="Close (Esc)"
          >
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {error ? (
            <ErrorNote message={error} />
          ) : !detail ? (
            <div className="flex items-center gap-2 p-4 text-sm text-zinc-400">
              <Spinner /> Loading variants…
            </div>
          ) : (
            detail.members.map((m) => (
              <Link
                key={m.ad_id}
                to={`/ad/${m.pipeline}/${m.competitor}/${m.ad_id}`}
                className="flex items-center gap-3 rounded-xl border border-transparent p-2 transition-colors hover:border-white/10 hover:bg-white/5"
              >
                <div className="h-20 w-14 shrink-0 overflow-hidden rounded-lg border border-white/10 bg-zinc-900">
                  {m.media_url ? (
                    <img
                      src={posterUrl(m)}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-lg opacity-30">
                      🎬
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <VerdictBadge verdict={m.verdict} />
                    {m.variant_role === 'original' && (
                      <span className="rounded-full border border-sky-400/30 bg-sky-500/15 px-2 py-0.5 text-[10px] font-medium text-sky-300">
                        original
                      </span>
                    )}
                    {m.status && <StatusChip status={m.status} />}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-zinc-300">
                    {m.language && <span className="font-medium">{m.language}</span>}
                    <span className="text-zinc-500">🔥 {runDaysLabel(m)}</span>
                    {!m.is_retired ? (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> live
                      </span>
                    ) : (
                      <span className="text-[10px] text-zinc-600">retired</span>
                    )}
                  </div>
                  {m.device_format && (
                    <div className="truncate text-[11px] text-zinc-500">{m.device_format}</div>
                  )}
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </>
  )
}

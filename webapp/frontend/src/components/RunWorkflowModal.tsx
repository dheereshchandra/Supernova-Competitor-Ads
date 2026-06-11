import { useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  getPipelinePending,
  runPipeline,
  type Competitor,
  type PipelinePending,
} from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/**
 * "Run data update" — scrape the latest ads (free) and enrich the ones still
 * pending (paid). The pending-enrichment count + cost is shown UPFRONT per
 * competitor (from already-scraped data); pick one or many competitors.
 */
export default function RunWorkflowModal({
  competitors,
  defaultPipeline,
  defaultCompetitor,
  onClose,
  onStarted,
}: {
  competitors: Competitor[]
  defaultPipeline: string
  defaultCompetitor?: string
  onClose: () => void
  onStarted: (jobIds: number[]) => void
}) {
  const [pipeline, setPipeline] = useState(defaultPipeline || 'facebook')
  const [pending, setPending] = useState<PipelinePending | null>(null)
  const [selected, setSelected] = useState<Set<string>>(
    new Set(defaultCompetitor ? [defaultCompetitor] : []),
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const options = useMemo(
    () => competitors.filter((c) => c.pipeline === pipeline),
    [competitors, pipeline],
  )

  useEffect(() => {
    let cancelled = false
    setPending(null)
    getPipelinePending(pipeline)
      .then((p) => !cancelled && setPending(p))
      .catch(() => !cancelled && setPending(null))
    return () => {
      cancelled = true
    }
  }, [pipeline])

  const perVideo = pending?.per_video_usd ?? 0.012
  const pendingOf = (slug: string) => pending?.per_competitor?.[slug] ?? 0
  const selectedPending = useMemo(
    () => [...selected].reduce((s, slug) => s + pendingOf(slug), 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected, pending],
  )
  const cost = +(selectedPending * perVideo).toFixed(2)

  const toggle = (slug: string) =>
    setSelected((prev) => {
      const n = new Set(prev)
      n.has(slug) ? n.delete(slug) : n.add(slug)
      return n
    })

  const run = async () => {
    setSubmitting(true)
    setError('')
    try {
      const r = await runPipeline(pipeline, [...selected])
      onStarted(r.job_ids)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message)
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="fade-in-up flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">↻ Run data update</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Scrapes the latest ads & refreshes rankings (free), then enriches the ads
          still pending — transcripts, language & format (≈{money(perVideo)}/ad). Pick
          one or many competitors.
        </p>

        <div className="mt-4 flex items-center gap-3">
          <label className="text-xs font-medium text-zinc-400">Platform</label>
          <select
            value={pipeline}
            onChange={(e) => {
              setPipeline(e.target.value)
              setSelected(new Set())
            }}
            className="rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-1.5 text-sm text-white outline-none focus:border-violet-400/50"
          >
            <option value="facebook">Facebook</option>
            <option value="google">Google</option>
          </select>
          <button
            onClick={() => setSelected(new Set(options.map((c) => c.slug)))}
            className="ml-auto text-xs text-violet-300 hover:underline"
          >
            Select all
          </button>
          <button
            onClick={() =>
              setSelected(new Set(options.filter((c) => pendingOf(c.slug) > 0).map((c) => c.slug)))
            }
            className="text-xs text-violet-300 hover:underline"
          >
            All with pending
          </button>
        </div>

        {/* competitor checklist */}
        <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950/40">
          {!pending ? (
            <div className="flex items-center gap-2 p-4 text-sm text-zinc-400">
              <Spinner /> Loading pending counts…
            </div>
          ) : (
            options.map((c) => {
              const n = pendingOf(c.slug)
              const on = selected.has(c.slug)
              return (
                <button
                  key={c.slug}
                  onClick={() => toggle(c.slug)}
                  className={`flex w-full items-center gap-3 border-b border-white/5 px-3 py-2 text-left text-sm transition-colors last:border-0 ${
                    on ? 'bg-violet-500/10' : 'hover:bg-white/5'
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                      on ? 'border-violet-400 bg-violet-500 text-white' : 'border-white/20'
                    }`}
                  >
                    {on ? '✓' : ''}
                  </span>
                  <span className="flex-1 truncate text-zinc-200">{c.page_name}</span>
                  {n > 0 ? (
                    <span className="shrink-0 text-xs text-amber-300">
                      {n.toLocaleString()} pending · {money(n * perVideo)}
                    </span>
                  ) : (
                    <span className="shrink-0 text-xs text-emerald-400/70">✓ all enriched</span>
                  )}
                </button>
              )
            })
          )}
        </div>

        {/* summary + cost */}
        <div className="mt-4 rounded-xl border border-white/10 bg-zinc-950/60 p-4">
          {selected.size === 0 ? (
            <div className="text-sm text-zinc-500">Pick competitors to refresh.</div>
          ) : selectedPending === 0 ? (
            <div className="text-sm text-emerald-300">
              ✓ All selected are enriched — nothing to enrich. Running will still scrape
              for brand-new ads (free).
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold tracking-tight text-white">
                  ≈ {money(cost)}
                </div>
                <div className="text-xs text-zinc-500">
                  {selectedPending.toLocaleString()} ads pending enrichment across{' '}
                  {selected.size} competitor{selected.size === 1 ? '' : 's'}
                </div>
              </div>
              <div className="text-right text-[11px] leading-tight text-zinc-500">
                scrape + rankings<br />
                <span className="text-emerald-400/80">free</span>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          >
            Cancel
          </button>
          <button
            onClick={run}
            disabled={submitting || selected.size === 0}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-50"
          >
            {submitting && <Spinner className="h-4 w-4 text-white" />}
            {selectedPending > 0 ? `Run & enrich for ≈ ${money(cost)}` : 'Run scrape (free)'}
          </button>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import {
  ApiError,
  getPipelineEstimate,
  runPipeline,
  type Competitor,
  type PipelineEstimate,
} from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/**
 * "Run data update" — runs the full pipeline (scrape → download → upload →
 * analysis → enrichment) for one competitor, EXCLUDING Supernova script
 * generation. Shows the approximate cost before the user commits.
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
  onStarted: (jobId: string) => void
}) {
  const [pipeline, setPipeline] = useState(defaultPipeline || 'facebook')
  const [competitor, setCompetitor] = useState(defaultCompetitor || '')
  const [estimate, setEstimate] = useState<PipelineEstimate | null>(null)
  const [estLoading, setEstLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const options = competitors.filter((c) => c.pipeline === pipeline)

  useEffect(() => {
    if (!competitor) {
      setEstimate(null)
      return
    }
    let cancelled = false
    setEstLoading(true)
    setError('')
    getPipelineEstimate(pipeline, competitor)
      .then((e) => !cancelled && setEstimate(e))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setEstLoading(false))
    return () => {
      cancelled = true
    }
  }, [pipeline, competitor])

  const confirm = async () => {
    setSubmitting(true)
    setError('')
    try {
      const r = await runPipeline(pipeline, competitor)
      onStarted(r.job_id)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message)
      setSubmitting(false)
    }
  }

  const ready = estimate?.eligible === true && !estLoading

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="fade-in-up w-full max-w-lg rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">↻ Run data update</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Pulls the latest ads, downloads new videos, recomputes rankings, and
          enriches them — so winners, ranks and verdicts reflect the newest data.
          (This does <span className="text-zinc-200">not</span> generate Supernova scripts.)
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <label className="text-xs font-medium text-zinc-400">
            Platform
            <select
              value={pipeline}
              onChange={(e) => {
                setPipeline(e.target.value)
                setCompetitor('')
              }}
              className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-white outline-none focus:border-violet-400/50"
            >
              <option value="facebook">Facebook</option>
              <option value="google">Google</option>
            </select>
          </label>
          <label className="text-xs font-medium text-zinc-400">
            Competitor
            <select
              value={competitor}
              onChange={(e) => setCompetitor(e.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-white outline-none focus:border-violet-400/50"
            >
              <option value="">Choose a competitor…</option>
              {options.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.page_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-5 min-h-[96px]">
          {!competitor ? (
            <div className="rounded-xl border border-white/10 bg-zinc-950/50 px-4 py-6 text-center text-sm text-zinc-500">
              Pick a competitor to see the cost.
            </div>
          ) : estLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-zinc-400">
              <Spinner /> Estimating cost…
            </div>
          ) : error && !estimate?.eligible ? (
            <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          ) : estimate?.eligible === false ? (
            <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              {estimate.reason}
            </div>
          ) : estimate ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-xl border border-white/10 bg-zinc-950/60 p-4">
                <div>
                  <div className="text-3xl font-bold tracking-tight text-white">
                    ≈ {money(estimate.cost_usd)}
                  </div>
                  <div className="text-xs text-zinc-500">
                    {estimate.backlog_videos} video{estimate.backlog_videos === 1 ? '' : 's'} to enrich · {estimate.wall_clock}
                  </div>
                </div>
                <div className="text-right text-[11px] leading-tight text-zinc-500">
                  scrape · download<br />upload · analysis<br />
                  <span className="text-emerald-400/80">all free</span>
                </div>
              </div>
              <p className="text-xs text-zinc-500">{estimate.note}</p>
            </div>
          ) : null}
        </div>

        {error && estimate?.eligible && (
          <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          >
            Cancel
          </button>
          {ready && (
            <button
              onClick={confirm}
              disabled={submitting}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
            >
              {submitting && <Spinner className="h-4 w-4 text-white" />}
              Run update {estimate?.cost_usd ? `for ≈ ${money(estimate.cost_usd)}` : ''}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

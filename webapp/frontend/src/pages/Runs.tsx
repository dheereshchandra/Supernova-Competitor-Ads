import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { cancelJob, getJobs, retryJob, type Job } from '../api'
import { elapsedBetween, JOB_STATUS_MAP, money, timeAgo } from '../format'
import { EmptyState, ErrorNote, PageLoading, Spinner } from '../components/ui'

export default function Runs() {
  const [jobs, setJobs] = useState<Job[] | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getJobs('recent')
      .then((r) => setJobs(r.jobs))
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    const t = window.setInterval(load, 3000)
    return () => window.clearInterval(t)
  }, [load])

  if (error) return <ErrorNote message={error} />
  if (!jobs) return <PageLoading label="Loading runs…" />
  if (jobs.length === 0) {
    return (
      <EmptyState
        icon="⚙️"
        title="No script runs yet"
        hint="When someone generates a Supernova script, its progress shows up here."
      />
    )
  }

  return (
    <div className="fade-in-up space-y-3">
      <h1 className="text-lg font-semibold text-white">Script runs</h1>
      {jobs.map((j) => (
        <RunCard key={j.id} job={j} onChange={load} />
      ))}
    </div>
  )
}

function RunCard({ job, onChange }: { job: Job; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const b = JOB_STATUS_MAP[job.status] ?? { label: job.status, className: '' }
  const total = job.steps.length
  const idx = job.step_index ?? (job.status === 'done' ? total : 0)
  const active = job.status === 'queued' || job.status === 'running'
  const curLabel = job.steps.find((s) => s.key === job.current_step)?.label

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/60 p-4">
      <div className="flex items-start gap-4">
        <Link
          to={`/ad/${job.pipeline}/${job.competitor}/${job.ad_id}`}
          className="shrink-0 text-sm font-medium text-zinc-200 hover:text-white"
        >
          <div className="text-zinc-100">{job.competitor}</div>
          <div className="text-xs text-zinc-500">#{job.ad_id.slice(-8)}</div>
        </Link>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${b.className}`}>
              {b.label}
            </span>
            {job.status === 'queued' && job.queue_position != null && (
              <span className="text-xs text-zinc-500">#{job.queue_position} in line</span>
            )}
            <span className="text-xs text-zinc-600">
              by {job.requested_by} · {timeAgo(job.created_at)}
            </span>
            {job.cost_estimate_usd != null && (
              <span className="text-xs text-zinc-500">{money(job.cost_estimate_usd)}</span>
            )}
          </div>

          {active && (
            <div className="mt-2">
              <div className="mb-1 flex items-center gap-2 text-xs text-zinc-400">
                {job.status === 'running' && <Spinner className="h-3 w-3" />}
                {curLabel || 'Waiting…'} · step {Math.min(idx + 1, total)}/{total}
                <span className="ml-auto text-zinc-600">
                  {elapsedBetween(job.started_at)}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-violet-500 transition-all"
                  style={{ width: `${(idx / total) * 100}%` }}
                />
              </div>
            </div>
          )}

          {job.status === 'done' && (
            <div className="mt-2 flex gap-2">
              {job.rewrite_gdoc_url && (
                <a href={job.rewrite_gdoc_url} target="_blank" rel="noreferrer"
                   className="rounded-lg bg-emerald-600/90 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500">
                  📝 Script
                </a>
              )}
              {job.analysis_gdoc_url && (
                <a href={job.analysis_gdoc_url} target="_blank" rel="noreferrer"
                   className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-300 hover:bg-white/5">
                  🔍 Analysis
                </a>
              )}
            </div>
          )}

          {(job.status === 'failed' || job.status === 'cancelled') && (
            <div className="mt-2">
              {job.error && <div className="text-xs text-red-300">{job.error}</div>}
              {job.stderr_tail && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-zinc-500">Show log</summary>
                  <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-black/60 p-2 text-[11px] leading-relaxed text-zinc-400">
                    {job.stderr_tail}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-col gap-1.5">
          {(job.status === 'failed' || job.status === 'cancelled') && (
            <button
              onClick={() => act(() => retryJob(job.id))}
              disabled={busy}
              className="rounded-lg bg-violet-600 px-3 py-1 text-xs font-semibold text-white hover:bg-violet-500 disabled:opacity-50"
            >
              Retry
            </button>
          )}
          {active && (
            <button
              onClick={() => act(() => cancelJob(job.id))}
              disabled={busy}
              className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-400 hover:bg-white/5 disabled:opacity-50"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

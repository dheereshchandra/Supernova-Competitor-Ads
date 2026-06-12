import { useEffect, useMemo, useState } from 'react'
import {
  adRef,
  bulkCreateJobs,
  bulkEstimate,
  type Ad,
  type BulkCreateResult,
  type BulkEstimateResult,
} from '../api'
import { money, posterUrl } from '../format'
import { Spinner } from './ui'

const REASON_LABELS: Record<string, string> = {
  facebook_only: 'Google ads not supported',
  not_found: 'not found',
  no_media: 'no media in R2',
  in_flight: 'already running',
  already_generated: 'docs exist',
  not_a_candidate: 'not eligible',
  job_cap: 'over the per-job cap',
  daily_cap: "over today's budget",
}

/**
 * Cost-gated bulk "Generate Supernova Scripts": one batch estimate up front
 * (per-ad price or the reason it can't run), the total vs today's remaining
 * budget, then enqueue. The server re-estimates and enqueues what fits the
 * daily cap, in order — the modal warns when not everything will fit.
 */
export default function BulkGenerateModal({
  ads,
  onClose,
  onStarted,
}: {
  ads: Ad[]
  onClose: () => void
  onStarted: (queued: number) => void
}) {
  const [est, setEst] = useState<BulkEstimateResult | null>(null)
  const [estError, setEstError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [result, setResult] = useState<BulkCreateResult | null>(null)

  const adsByKey = useMemo(
    () => new Map(ads.map((a) => [`${a.pipeline}/${a.competitor}/${a.ad_id}`, a])),
    [ads],
  )

  useEffect(() => {
    let cancelled = false
    bulkEstimate(ads.map(adRef))
      .then((e) => !cancelled && setEst(e))
      .catch((e: Error) => !cancelled && setEstError(e.message || 'Could not get prices'))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const eligible = useMemo(() => (est?.items ?? []).filter((i) => i.eligible), [est])
  // Same greedy walk the server does at enqueue time: in order, skip what
  // no longer fits today's remaining budget.
  const fit = useMemo(() => {
    if (!est) return { count: 0, cost: 0 }
    let cost = 0
    let count = 0
    for (const i of eligible) {
      const c = i.cost_usd ?? 0
      if (cost + c <= est.daily_remaining_usd) {
        cost += c
        count += 1
      }
    }
    return { count, cost }
  }, [est, eligible])

  const confirm = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const r = await bulkCreateJobs(eligible.map(adRef))
      setResult(r)
    } catch (e) {
      setSubmitError((e as Error).message || 'Something went wrong')
    } finally {
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
        <h2 className="text-lg font-semibold text-white">
          ✨ Generate {ads.length} Supernova Script{ads.length === 1 ? '' : 's'}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {result
            ? 'Done — the queue runs one script at a time; watch progress in Runs.'
            : 'Each ad gets its own script docs. Scripts are generated one at a time, in order.'}
        </p>

        {/* per-ad list */}
        <div className="mt-4 min-h-0 flex-1 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950/40">
          {estError ? (
            <div className="p-4 text-sm text-red-300">{estError}</div>
          ) : !est ? (
            <div className="flex items-center gap-2 p-4 text-sm text-zinc-400">
              <Spinner /> Working out the prices…
            </div>
          ) : (
            est.items.map((i) => {
              const key = `${i.pipeline}/${i.competitor}/${i.ad_id}`
              const ad = adsByKey.get(key)
              const queued = result?.queued.find((q) => q.ad_id === i.ad_id)
              const skippedNow = result?.skipped.find((s) => s.ad_id === i.ad_id)
              return (
                <div
                  key={key}
                  className="flex items-center gap-3 border-b border-white/5 px-3 py-2 text-sm last:border-0"
                >
                  <div className="h-12 w-9 shrink-0 overflow-hidden rounded border border-white/10 bg-zinc-900">
                    {ad?.media_url && (
                      <img src={posterUrl(ad)} alt="" loading="lazy" className="h-full w-full object-cover" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-zinc-200">{i.competitor}</div>
                    <div className="truncate text-[11px] text-zinc-500">{i.ad_id}</div>
                  </div>
                  {result ? (
                    queued ? (
                      <span className="shrink-0 text-xs font-medium text-emerald-300">
                        ✓ queued · {money(queued.cost_usd)}
                      </span>
                    ) : (
                      <span className="shrink-0 text-xs text-zinc-500">
                        {REASON_LABELS[skippedNow?.reason ?? i.reason ?? ''] ??
                          skippedNow?.reason ?? i.reason ?? 'skipped'}
                      </span>
                    )
                  ) : i.eligible ? (
                    <span className="shrink-0 text-xs font-medium text-zinc-200">
                      {money(i.cost_usd)}
                    </span>
                  ) : (
                    <span className="shrink-0 text-xs text-zinc-500">
                      {REASON_LABELS[i.reason ?? ''] ?? i.reason}
                    </span>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* summary */}
        {est && !result && (
          <div className="mt-4 rounded-xl border border-white/10 bg-zinc-950/60 p-4">
            {eligible.length === 0 ? (
              <div className="text-sm text-zinc-500">
                None of the selected ads can be generated right now.
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-2xl font-bold tracking-tight text-white">
                      ≈ {money(est.total_cost_usd)}
                    </div>
                    <div className="text-xs text-zinc-500">
                      {eligible.length} script{eligible.length === 1 ? '' : 's'} · one-time AI cost
                    </div>
                  </div>
                  <div className="text-right text-[11px] leading-tight text-zinc-500">
                    today's remaining budget
                    <br />
                    <span className="text-zinc-300">{money(est.daily_remaining_usd)}</span>
                  </div>
                </div>
                {fit.count < eligible.length && (
                  <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                    Only the first {fit.count} fit today's budget — the rest will be
                    skipped. They can be queued again tomorrow.
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {result && (
          <div className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            Queued {result.queued.length} script{result.queued.length === 1 ? '' : 's'} for ≈{' '}
            {money(result.total_queued_usd)}
            {result.skipped.length > 0 && (
              <span className="text-emerald-200/70"> · {result.skipped.length} skipped</span>
            )}
          </div>
        )}

        {submitError && (
          <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
            {submitError}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          {result ? (
            <button
              onClick={() => onStarted(result.queued.length)}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
              >
                Cancel
              </button>
              {est && eligible.length > 0 && (
                <button
                  onClick={confirm}
                  disabled={submitting || fit.count === 0}
                  title={fit.count === 0 ? "Today's budget is used up — try tomorrow" : undefined}
                  className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
                >
                  {submitting && <Spinner className="h-4 w-4 text-white" />}
                  Queue {fit.count} script{fit.count === 1 ? '' : 's'} for ≈{' '}
                  {money(fit.cost)}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

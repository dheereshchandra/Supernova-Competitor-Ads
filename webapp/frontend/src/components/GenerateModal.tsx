import { useEffect, useState } from 'react'
import {
  ApiError,
  createJob,
  getEstimate,
  type Estimate,
} from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/**
 * Cost-gated "Generate Supernova Script" confirmation.
 * Fetches the live estimate on open; the confirm button shows the real price.
 */
export default function GenerateModal({
  pipeline,
  competitor,
  adId,
  force = false,
  onClose,
  onStarted,
}: {
  pipeline: string
  competitor: string
  adId: string
  force?: boolean
  onClose: () => void
  onStarted: (jobId: string) => void
}) {
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [estimateError, setEstimateError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  useEffect(() => {
    let cancelled = false
    getEstimate(pipeline, competitor, adId)
      .then((e) => {
        if (!cancelled) setEstimate(e)
      })
      .catch((e: Error) => {
        if (!cancelled) setEstimateError(e.message || 'Could not get a price')
      })
    return () => {
      cancelled = true
    }
  }, [pipeline, competitor, adId])

  const confirm = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const r = await createJob(pipeline, competitor, adId, force)
      onStarted(r.job_id)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setSubmitError(e.detail)
      } else if (e instanceof ApiError && e.status === 404) {
        setSubmitError(
          'The generation service is still warming up — please try again in a few minutes.',
        )
      } else {
        setSubmitError((e as Error).message || 'Something went wrong')
      }
      setSubmitting(false)
    }
  }

  const eligible = estimate?.eligible === true && !estimateError

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="fade-in-up w-full max-w-md rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">
          ✨ Generate Supernova Script
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          We'll break down this competitor ad and write a Supernova version of the
          script, with visuals, into shareable docs.
        </p>

        <div className="mt-5">
          {estimateError ? (
            <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {estimateError}
            </div>
          ) : !estimate ? (
            <div className="flex items-center gap-2 py-6 text-sm text-zinc-400">
              <Spinner /> Working out the price…
            </div>
          ) : !estimate.eligible ? (
            <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              {estimate.already_generated
                ? 'A script was already generated for this ad. You can open the existing docs from the ad page.'
                : (estimate.reason ?? "This ad can't be generated right now.")}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-center">
                <div className="text-4xl font-bold tracking-tight text-white">
                  {money(estimate.cost_usd)}
                </div>
                <div className="mt-1 text-xs text-zinc-500">one-time AI cost</div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <div className="rounded-lg bg-white/5 px-2 py-2">
                  <div className="font-semibold text-zinc-200">
                    {estimate.duration_s != null ? `${estimate.duration_s}s` : '—'}
                  </div>
                  <div className="text-[11px] text-zinc-500">video length</div>
                </div>
                <div className="rounded-lg bg-white/5 px-2 py-2">
                  <div className="font-semibold text-zinc-200">
                    {estimate.scenes ?? '—'}
                  </div>
                  <div className="text-[11px] text-zinc-500">scenes</div>
                </div>
                <div className="rounded-lg bg-white/5 px-2 py-2">
                  <div className="font-semibold text-zinc-200">
                    {estimate.wall_clock ?? '5–20 min'}
                  </div>
                  <div className="text-[11px] text-zinc-500">takes about</div>
                </div>
              </div>
              <p className="text-xs text-zinc-500">
                Team spend so far this month:{' '}
                <span className="text-zinc-300">{money(estimate.month_to_date_usd)}</span>
                {estimate.notes ? <> · {estimate.notes}</> : null}
              </p>
              {force && (
                <p className="rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  This will re-generate and replace the existing docs.
                </p>
              )}
            </div>
          )}

          {submitError && (
            <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {submitError}
            </div>
          )}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          >
            Cancel
          </button>
          {eligible && estimate && (
            <button
              onClick={confirm}
              disabled={submitting}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
            >
              {submitting && <Spinner className="h-4 w-4 text-white" />}
              Generate for {money(estimate.cost_usd)}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

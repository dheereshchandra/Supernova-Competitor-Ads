import { useEffect, useState } from 'react'
import {
  adRef,
  bulkLocalize,
  bulkLocalizeEstimate,
  SUPPORTED_LANGUAGES,
  type Ad,
  type BulkCreateResult,
  type BulkLocalizeEstimate,
} from '../api'
import { money } from '../format'
import { Spinner } from './ui'

const REASON_LABELS: Record<string, string> = {
  facebook_only: 'Google ads not supported',
  not_found: 'not found',
  no_english_script: 'no English script yet',
  in_flight: 'already running',
  daily_cap: "over today's budget",
}

/**
 * Bulk "Replicate to languages": one language set applied to every selected ad
 * (each ad becomes its own localize job). Only ads that already have an English
 * Supernova script are eligible; the visuals are reused, so images cost ₹0.
 */
export default function BulkLocalizeModal({
  ads,
  onClose,
  onStarted,
}: {
  ads: Ad[]
  onClose: () => void
  onStarted: (queued: number) => void
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [consented, setConsented] = useState(false)
  const [est, setEst] = useState<BulkLocalizeEstimate | null>(null)
  const [estError, setEstError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [result, setResult] = useState<BulkCreateResult | null>(null)

  const langs = [...selected]

  useEffect(() => {
    if (langs.length === 0) {
      setEst(null)
      return
    }
    let cancelled = false
    bulkLocalizeEstimate(ads.map(adRef), langs)
      .then((e) => !cancelled && setEst(e))
      .catch((e: Error) => !cancelled && setEstError(e.message || 'Could not get prices'))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  const toggle = (lang: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })

  const eligible = (est?.items ?? []).filter((i) => i.eligible)
  const skipped = (est?.items ?? []).filter((i) => !i.eligible)

  const confirm = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const r = await bulkLocalize(eligible.map((i) => adRef(i)), langs)
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
        className="fade-in-up max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">
          🌍 Replicate {ads.length} ad{ads.length === 1 ? '' : 's'} to languages
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          One language set for all selected ads — each ad becomes its own job. Visuals are
          reused (images ₹0); only ads with an English script are eligible.
        </p>

        {result ? (
          <div className="mt-5 space-y-3">
            <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              Queued {result.queued.length} job{result.queued.length === 1 ? '' : 's'} (
              {money(result.total_queued_usd)}).
              {result.skipped.length > 0 && ` Skipped ${result.skipped.length}.`}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => onStarted(result.queued.length)}
                className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap gap-2">
              {SUPPORTED_LANGUAGES.map((lang) => {
                const on = selected.has(lang)
                return (
                  <button
                    key={lang}
                    onClick={() => toggle(lang)}
                    className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                      on
                        ? 'border-violet-400/40 bg-violet-600/30 text-violet-100'
                        : 'border-white/10 bg-white/5 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {lang}
                  </button>
                )
              })}
            </div>

            <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-xl border border-white/10 bg-zinc-950/60 p-3 text-sm text-zinc-300">
              <input
                type="checkbox"
                checked={consented}
                onChange={(e) => setConsented(e.target.checked)}
                className="mt-0.5 accent-violet-500"
              />
              <span>
                The <b>English script Docs</b> for these ads are reviewed — edits are final.
              </span>
            </label>

            <div className="mt-4">
              {estError ? (
                <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {estError}
                </div>
              ) : langs.length === 0 ? (
                <div className="py-3 text-center text-sm text-zinc-500">
                  Pick at least one language.
                </div>
              ) : !est ? (
                <div className="flex items-center gap-2 py-3 text-sm text-zinc-400">
                  <Spinner /> Working out the price…
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-center">
                    <div className="text-3xl font-bold tracking-tight text-white">
                      {money(est.total_cost_usd)}
                    </div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {eligible.length} ad{eligible.length === 1 ? '' : 's'} ×{' '}
                      {langs.length} language{langs.length === 1 ? '' : 's'} · images ₹0
                      (reused) · {money(est.daily_remaining_usd)} left in today's budget
                    </div>
                  </div>
                  {skipped.length > 0 && (
                    <div className="rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                      Skipping {skipped.length}:{' '}
                      {skipped
                        .map(
                          (s) =>
                            `${s.ad_id.slice(0, 8)}… (${REASON_LABELS[s.reason ?? ''] ?? s.reason})`,
                        )
                        .join(', ')}
                    </div>
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
              <button
                onClick={confirm}
                disabled={submitting || !consented || langs.length === 0 || eligible.length === 0}
                className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
              >
                {submitting && <Spinner className="h-4 w-4 text-white" />}
                Replicate {eligible.length || ''} ad{eligible.length === 1 ? '' : 's'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

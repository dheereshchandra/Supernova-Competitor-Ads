import { useEffect, useState } from 'react'
import {
  ApiError,
  createJob,
  getEstimate,
  SUPPORTED_LANGUAGES,
  type Estimate,
} from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/** Matches LOCALIZE_COST_PER_LANG on the backend (Flash translate + safety audit, images reused). */
const COST_PER_LANG_USD = 0.02

/**
 * Cost-gated "Generate Supernova Script" confirmation.
 * Fetches the live estimate on open; the confirm button shows the real price.
 * Generate produces ONE combined Doc per chosen language (English + that language) — pick ≥1.
 */
export default function GenerateModal({
  pipeline,
  competitor,
  adId,
  force = false,
  suggestedLanguages = [],
  onClose,
  onStarted,
}: {
  pipeline: string
  competitor: string
  adId: string
  force?: boolean
  /** pre-tick these (e.g. the languages the competitor's script-group runs in) */
  suggestedLanguages?: string[]
  onClose: () => void
  onStarted: (jobId: string) => void
}) {
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [estimateError, setEstimateError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [conceptBrief, setConceptBrief] = useState('')
  const [selected, setSelected] = useState<Set<string>>(
    () =>
      new Set(
        suggestedLanguages.filter((l) =>
          (SUPPORTED_LANGUAGES as readonly string[]).includes(l),
        ),
      ),
  )

  const toggleLang = (lang: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })

  const langs = [...selected]

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
      const r = await createJob(pipeline, competitor, adId, force, conceptBrief, langs)
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
          We'll break down this competitor ad and write a Supernova version of the script.
          Pick the languages — you get <span className="text-zinc-200">one Doc per language</span>,
          each with the English and that language's script side by side.
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
                  {money((estimate.cost_usd ?? 0) + langs.length * COST_PER_LANG_USD)}
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  one-time AI cost
                  {langs.length > 0 && (
                    <> · script + {langs.length} language{langs.length === 1 ? '' : 's'}</>
                  )}
                </div>
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
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-300">
                  Concept brief{' '}
                  <span className="font-normal text-zinc-500">(optional — replication direction)</span>
                </label>
                <textarea
                  value={conceptBrief}
                  onChange={(e) => setConceptBrief(e.target.value)}
                  rows={3}
                  placeholder="e.g. Replace the man with a baby; treat the ASMR split-screen as a single talking-head; keep the hook…"
                  className="w-full resize-y rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-violet-500/50 focus:outline-none"
                />
                <p className="mt-1 text-[11px] text-zinc-500">
                  Character swaps, format changes, ASMR→talking-head — followed over the competitor's original.
                </p>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Languages <span className="font-normal text-zinc-500">(pick at least one)</span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {SUPPORTED_LANGUAGES.map((lang) => {
                    const on = selected.has(lang)
                    return (
                      <button
                        key={lang}
                        type="button"
                        onClick={() => toggleLang(lang)}
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
                <p className="mt-1.5 text-[11px] text-zinc-500">
                  One Google Doc per language — English + that language together. Add more later
                  from the ad page.
                </p>
              </div>
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
              disabled={submitting || langs.length === 0}
              title={langs.length === 0 ? 'Pick at least one language' : undefined}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
            >
              {submitting && <Spinner className="h-4 w-4 text-white" />}
              Generate for {money((estimate.cost_usd ?? 0) + langs.length * COST_PER_LANG_USD)}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { ApiError, createLocalizeJob, SUPPORTED_LANGUAGES } from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/** Matches LOCALIZE_COST_PER_LANG on the backend (Flash translate + safety audit). */
const COST_PER_LANG_USD = 0.02

/**
 * "Replicate to languages" confirmation: pick target languages, consent that the
 * English Doc was reviewed (its edits are the source of truth), see the price.
 * Images are NEVER regenerated — localization reuses the ad's existing visuals.
 */
export default function LocalizeModal({
  pipeline,
  competitor,
  adId,
  suggestedLanguages = [],
  alreadyLocalized = [],
  onClose,
  onStarted,
}: {
  pipeline: string
  competitor: string
  adId: string
  /** pre-tick these (e.g. the languages the competitor's own script-group runs in) */
  suggestedLanguages?: string[]
  /** languages that already have a localized Doc (shown as re-runs) */
  alreadyLocalized?: string[]
  onClose: () => void
  onStarted: (jobId: string) => void
}) {
  const [selected, setSelected] = useState<Set<string>>(
    () =>
      new Set(
        suggestedLanguages.filter((l) =>
          (SUPPORTED_LANGUAGES as readonly string[]).includes(l),
        ),
      ),
  )
  const [consented, setConsented] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const toggle = (lang: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })
  }

  const langs = [...selected]
  const cost = langs.length * COST_PER_LANG_USD

  const confirm = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const force = langs.some((l) => alreadyLocalized.includes(l))
      const r = await createLocalizeJob(pipeline, competitor, adId, langs, force)
      onStarted(r.job_id)
    } catch (e) {
      setSubmitError(
        e instanceof ApiError ? e.detail : (e as Error).message || 'Something went wrong',
      )
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="fade-in-up w-full max-w-md rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">🌍 Replicate to languages</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Translates the <span className="text-zinc-200">edited English Doc</span> (your
          edits + comments are read live) into each language as its own Google Doc. The
          visuals are reused — images cost ₹0.
        </p>

        <div className="mt-4 flex flex-wrap gap-2">
          {SUPPORTED_LANGUAGES.map((lang) => {
            const on = selected.has(lang)
            const rerun = alreadyLocalized.includes(lang)
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
                {rerun && <span className="ml-1 text-[10px] text-amber-300">↻</span>}
              </button>
            )
          })}
        </div>
        {alreadyLocalized.length > 0 && (
          <p className="mt-2 text-[11px] text-amber-200/80">
            ↻ = already localized; selecting it re-translates and updates that Doc.
          </p>
        )}

        <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-xl border border-white/10 bg-zinc-950/60 p-3 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={consented}
            onChange={(e) => setConsented(e.target.checked)}
            className="mt-0.5 accent-violet-500"
          />
          <span>
            I've reviewed the <b>English script Doc</b> — edits are final and comments are
            ready to be applied during translation.
          </span>
        </label>

        <div className="mt-4 rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-center">
          <div className="text-3xl font-bold tracking-tight text-white">
            {langs.length ? money(cost) : '—'}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {langs.length} language{langs.length === 1 ? '' : 's'} · text only · images ₹0
            (reused)
          </div>
        </div>

        {submitError && (
          <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {submitError}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={submitting || !consented || langs.length === 0}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
          >
            {submitting && <Spinner className="h-4 w-4 text-white" />}
            Replicate{langs.length ? ` into ${langs.length}` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}

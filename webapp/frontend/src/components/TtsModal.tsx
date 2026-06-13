import { useState } from 'react'
import { ApiError, createTtsJob, TTS_LANGUAGES } from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/** Approx; matches TTS_COST_PER_LANG (per-language voiceover) on the backend. */
const COST_PER_LANG_USD = 0.25

/**
 * "Generate voiceover" confirmation: pick languages, confirm the scripts are final
 * (TTS reads them verbatim; per-character voices come from the registry), see the price.
 */
export default function TtsModal({
  pipeline,
  competitor,
  adId,
  suggestedLanguages = [],
  alreadyTts = [],
  onClose,
  onStarted,
}: {
  pipeline: string
  competitor: string
  adId: string
  /** pre-tick these (e.g. the languages this ad already has scripts for) */
  suggestedLanguages?: string[]
  /** languages that already have a voiceover (shown as re-runs) */
  alreadyTts?: string[]
  onClose: () => void
  onStarted: (jobId: string) => void
}) {
  const [selected, setSelected] = useState<Set<string>>(
    () =>
      new Set(
        suggestedLanguages.filter((l) => (TTS_LANGUAGES as readonly string[]).includes(l)),
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
      const force = langs.some((l) => alreadyTts.includes(l))
      const r = await createTtsJob(pipeline, competitor, adId, langs, force)
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
        <h2 className="text-lg font-semibold text-white">🔊 Generate voiceover</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Synthesizes a voiceover for each language from its{' '}
          <span className="text-zinc-200">approved script</span> — one voice per character
          (Miss Nova + cast) from the voice registry. English reads the master; other
          languages read the localized script.
        </p>

        <div className="mt-4 flex flex-wrap gap-2">
          {TTS_LANGUAGES.map((lang) => {
            const on = selected.has(lang)
            const rerun = alreadyTts.includes(lang)
            return (
              <button
                key={lang}
                onClick={() => toggle(lang)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                  on
                    ? 'border-sky-400/40 bg-sky-600/30 text-sky-100'
                    : 'border-white/10 bg-white/5 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {lang}
                {rerun && <span className="ml-1 text-[10px] text-amber-300">↻</span>}
              </button>
            )
          })}
        </div>
        {alreadyTts.length > 0 && (
          <p className="mt-2 text-[11px] text-amber-200/80">
            ↻ = already has a voiceover; selecting it re-synthesizes.
          </p>
        )}

        <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-xl border border-white/10 bg-zinc-950/60 p-3 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={consented}
            onChange={(e) => setConsented(e.target.checked)}
            className="mt-0.5 accent-sky-500"
          />
          <span>
            I've reviewed the <b>script for each chosen language</b> — TTS reads it verbatim.
          </span>
        </label>

        <div className="mt-4 rounded-xl border border-white/10 bg-zinc-950/60 p-4 text-center">
          <div className="text-3xl font-bold tracking-tight text-white">
            {langs.length ? money(cost) : '—'}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {langs.length} language{langs.length === 1 ? '' : 's'} · est. voiceover cost
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
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-sky-950/50 transition-colors hover:bg-sky-500 disabled:opacity-60"
          >
            {submitting && <Spinner className="h-4 w-4 text-white" />}
            Generate{langs.length ? ` ${langs.length}` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}

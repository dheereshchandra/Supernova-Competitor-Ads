import { useEffect, useState } from 'react'
import { ApiError, createTtsJob, getTtsSetup, type TtsSetup, TTS_LANGUAGES } from '../api'
import { money } from '../format'
import { Spinner } from './ui'

/** Voiceover is billed per CHARACTER at the provider, so cost depends on script length AND on
 * which provider each character's voice is on:
 *   Cartesia  ≈ $7.5 / 1M chars   (cheaper)
 *   ElevenLabs ≈ $165 / 1M chars  (premium)
 * We split an estimated ~1.2k chars/language across the cast and price each by its chosen voice. */
const AVG_CHARS_PER_LANG = 1200
const RATE_PER_M: Record<string, number> = { cartesia: 7.5, elevenlabs: 165 }
const PROVIDER_LABEL: Record<string, string> = {
  cartesia: 'Cartesia (cheaper)',
  elevenlabs: 'ElevenLabs (premium)',
}

/**
 * "Generate voiceover" confirmation: pick languages, pick a voice per character (same or
 * different), confirm the scripts are final, see the cost from the chosen voices.
 */
export default function TtsModal({
  pipeline,
  competitor,
  adId,
  suggestedLanguages = [],
  alreadyTts = [],
  remarks = [],
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
  /** ad-level edge-case notes (English-original / no-voiceover) — must be acknowledged before TTS */
  remarks?: string[]
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
  const [ackRemarks, setAckRemarks] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [setup, setSetup] = useState<TtsSetup | null>(null)
  const [loadingSetup, setLoadingSetup] = useState(false)
  /** character name -> chosen voice_id */
  const [picks, setPicks] = useState<Record<string, string>>({})

  const toggle = (lang: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })
  }

  const langs = [...selected]
  const firstLang = langs[0] ?? ''

  // Load the cast + voice catalog for the first selected language; default each pick to the
  // auto-assigned voice. (Cast is the same across languages; defaults are language-specific.)
  useEffect(() => {
    if (!firstLang) {
      setSetup(null)
      return
    }
    let cancelled = false
    setLoadingSetup(true)
    getTtsSetup(pipeline, competitor, adId, firstLang)
      .then((s) => {
        if (cancelled) return
        setSetup(s)
        setPicks(Object.fromEntries(s.characters.map((c) => [c.name, c.default_voice_id])))
      })
      .catch(() => {
        if (!cancelled) setSetup(null)
      })
      .finally(() => {
        if (!cancelled) setLoadingSetup(false)
      })
    return () => {
      cancelled = true
    }
  }, [pipeline, competitor, adId, firstLang])

  const voiceById = new Map((setup?.voices ?? []).map((v) => [v.voice_id, v]))
  const nChars = Math.max(1, setup?.characters.length ?? 1)
  const perCharChars = AVG_CHARS_PER_LANG / nChars
  const costPerLang = setup
    ? setup.characters.reduce((sum, c) => {
        const vid = picks[c.name] ?? c.default_voice_id
        const prov = voiceById.get(vid)?.provider ?? 'elevenlabs'
        return sum + (perCharChars * (RATE_PER_M[prov] ?? 165)) / 1_000_000
      }, 0)
    : 0
  const cost = costPerLang * langs.length

  const confirm = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const force = langs.some((l) => alreadyTts.includes(l))
      const r = await createTtsJob(pipeline, competitor, adId, langs, force, picks)
      onStarted(r.job_id)
    } catch (e) {
      setSubmitError(
        e instanceof ApiError ? e.detail : (e as Error).message || 'Something went wrong',
      )
      setSubmitting(false)
    }
  }

  const providers = ['cartesia', 'elevenlabs']

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="fade-in-up max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-white">🔊 Generate voiceover</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Synthesizes a voiceover for each language from its{' '}
          <span className="text-zinc-200">approved script</span>. Pick a voice per character
          below — set the same voice for several to reuse it.
        </p>

        {remarks.length > 0 && (
          <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100">
            <input
              type="checkbox"
              checked={ackRemarks}
              onChange={(e) => setAckRemarks(e.target.checked)}
              className="mt-0.5 accent-amber-500"
            />
            <span>
              <span className="font-semibold">
                ⚠️ Reviewer note{remarks.length > 1 ? 's' : ''}:
              </span>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {remarks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <span className="mt-1.5 block text-amber-200/80">
                I understand — generate the voiceover anyway.
              </span>
            </span>
          </label>
        )}

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

        {/* Per-character voice picker */}
        {firstLang && (
          <div className="mt-4">
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Voices
              </span>
              {loadingSetup && <Spinner className="h-3 w-3 text-zinc-500" />}
            </div>
            {setup && setup.characters.length > 0 ? (
              <div className="space-y-2">
                {setup.characters.map((c) => (
                  <div key={c.name} className="flex items-center gap-2">
                    <div className="w-24 shrink-0 truncate text-sm text-zinc-300" title={c.role}>
                      {c.name}
                    </div>
                    <select
                      value={picks[c.name] ?? c.default_voice_id}
                      onChange={(e) =>
                        setPicks((p) => ({ ...p, [c.name]: e.target.value }))
                      }
                      className="min-w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/60 px-2 py-1.5 text-sm text-zinc-100 focus:border-sky-500/50 focus:outline-none"
                    >
                      {providers.map((prov) => (
                        <optgroup key={prov} label={PROVIDER_LABEL[prov]}>
                          {setup.voices
                            .filter((v) => v.provider === prov)
                            .map((v) => (
                              <option key={v.voice_id} value={v.voice_id}>
                                {v.name}
                              </option>
                            ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                ))}
                <p className="text-[11px] text-zinc-500">
                  Defaults auto-assigned for {firstLang}. Cartesia is cheaper; ElevenLabs is premium.
                </p>
              </div>
            ) : (
              !loadingSetup && (
                <p className="text-[11px] text-zinc-500">
                  Using the registry's default voices for each character.
                </p>
              )
            )}
          </div>
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
            {langs.length && setup ? `≈ ${money(cost)}` : '—'}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {langs.length} language{langs.length === 1 ? '' : 's'} · from your voice picks
            (Cartesia ~${RATE_PER_M.cartesia}/1M chars · ElevenLabs ~${RATE_PER_M.elevenlabs}/1M)
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
            disabled={
              submitting ||
              !consented ||
              (remarks.length > 0 && !ackRemarks) ||
              langs.length === 0
            }
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

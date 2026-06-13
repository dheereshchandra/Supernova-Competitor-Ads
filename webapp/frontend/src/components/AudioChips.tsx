import { useState } from 'react'
import { type LangVerify, verifyTtsLanguage } from '../api'

/**
 * Per-language voiceover (TTS) chips: an inline audio player + a verify toggle.
 * Each language is verified by its owner (recorded + displayed, not enforced) —
 * mirrors LocalizedDocsChips for the audio stage (Workflow Stage 5a).
 */
export default function AudioChips({
  pipeline,
  competitor,
  adId,
  audio,
  verified,
  onChanged,
}: {
  pipeline: string
  competitor: string
  adId: string
  /** { Hindi: trackUrl, … } */
  audio: Record<string, string>
  /** { Hindi: { verified, verified_by, at }, … } */
  verified: Record<string, LangVerify>
  onChanged: (v: Record<string, LangVerify>) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const langs = Object.keys(audio).filter((l) => audio[l]).sort()
  if (langs.length === 0) return null

  const toggle = async (lang: string) => {
    const cur = verified[lang]?.verified === true
    setBusy(lang)
    try {
      const r = await verifyTtsLanguage(pipeline, competitor, adId, lang, !cur)
      onChanged(r.tts_verified_languages)
    } catch {
      /* leave state unchanged; next refresh corrects it */
    } finally {
      setBusy(null)
    }
  }

  const done = langs.filter((l) => verified[l]?.verified).length

  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Voiceovers
        </span>
        <span className="text-[11px] text-zinc-500">
          {done}/{langs.length} verified
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {langs.map((lang) => {
          const v = verified[lang]
          const ok = v?.verified === true
          return (
            <div
              key={lang}
              className={`flex items-center gap-2 rounded-lg border px-2 py-1 text-xs ${
                ok ? 'border-emerald-400/30 bg-emerald-500/10' : 'border-white/10 bg-white/5'
              }`}
            >
              <span
                className={`w-20 shrink-0 font-medium ${ok ? 'text-emerald-200' : 'text-zinc-300'}`}
              >
                🔊 {lang}
              </span>
              <audio controls preload="none" src={audio[lang]} className="h-8 min-w-0 flex-1" />
              <button
                onClick={() => toggle(lang)}
                disabled={busy === lang}
                title={
                  ok
                    ? `Verified by ${v?.verified_by || '?'}${v?.at ? ` · ${v.at}` : ''} — click to unverify`
                    : 'Mark this voiceover as verified (you become the verifier)'
                }
                className={`shrink-0 rounded px-1 py-0.5 text-[11px] transition-colors disabled:opacity-50 ${
                  ok ? 'text-emerald-300 hover:text-emerald-100' : 'text-zinc-500 hover:text-zinc-200'
                }`}
              >
                {ok ? `✓ ${v?.verified_by || 'verified'}` : 'verify'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

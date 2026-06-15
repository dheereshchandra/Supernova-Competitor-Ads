import { useState } from 'react'
import { type LangVerify, verifyLocalizeLanguage } from '../api'

/**
 * Per-language localized-script chips: open the Doc + a verify toggle.
 * Each language is verified by its language owner (recorded + displayed, not enforced).
 */
/** brand-safety verdict -> reviewer-focused badge (every script still gets human review;
 * this only says how much focus + what to check). */
const REVIEW_BADGE: Record<string, { emoji: string; label: string }> = {
  block: { emoji: '🔴', label: 'Priority review' },
  flag: { emoji: '🟡', label: 'Review suggested' },
  pass: { emoji: '🟢', label: 'Standard' },
}

export default function LocalizedDocsChips({
  pipeline,
  competitor,
  adId,
  locales,
  review = {},
  verified,
  onChanged,
}: {
  pipeline: string
  competitor: string
  adId: string
  /** { Hindi: docUrl, … } */
  locales: Record<string, string>
  /** { Hindi: { verdict: 'pass'|'flag'|'block', notes }, … } — reviewer signal */
  review?: Record<string, { verdict: string; notes: string }>
  /** { Hindi: { verified, verified_by, at }, … } */
  verified: Record<string, LangVerify>
  onChanged: (v: Record<string, LangVerify>) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const langs = Object.keys(locales).sort()
  if (langs.length === 0) return null

  const toggle = async (lang: string) => {
    const cur = verified[lang]?.verified === true
    setBusy(lang)
    try {
      const r = await verifyLocalizeLanguage(pipeline, competitor, adId, lang, !cur)
      onChanged(r.verified_languages)
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
          Localized scripts
        </span>
        <span className="text-[11px] text-zinc-500">
          {done}/{langs.length} verified
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {langs.map((lang) => {
          const v = verified[lang]
          const ok = v?.verified === true
          return (
            <span
              key={lang}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs ${
                ok
                  ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
                  : 'border-white/10 bg-white/5 text-zinc-300'
              }`}
            >
              <a
                href={locales[lang]}
                target="_blank"
                rel="noreferrer"
                className="font-medium hover:underline"
                title={`Open the ${lang} script Doc`}
              >
                📄 {lang}
              </a>
              {(() => {
                const r = review[lang]
                const meta = r && REVIEW_BADGE[r.verdict]
                if (!meta) return null
                return (
                  <span
                    className="cursor-help text-[11px] leading-none"
                    title={`${meta.label}${r.notes ? ` — ${r.notes}` : ''}`}
                  >
                    {meta.emoji}
                  </span>
                )
              })()}
              <button
                onClick={() => toggle(lang)}
                disabled={busy === lang}
                title={
                  ok
                    ? `Verified by ${v?.verified_by || '?'}${v?.at ? ` · ${v.at}` : ''} — click to unverify`
                    : 'Mark this language as verified (you become the verifier)'
                }
                className={`rounded px-1 py-0.5 text-[11px] transition-colors disabled:opacity-50 ${
                  ok ? 'text-emerald-300 hover:text-emerald-100' : 'text-zinc-500 hover:text-zinc-200'
                }`}
              >
                {ok ? `✓ ${v?.verified_by || 'verified'}` : 'verify'}
              </button>
            </span>
          )
        })}
      </div>
    </div>
  )
}

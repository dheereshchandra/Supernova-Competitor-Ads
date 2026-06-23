import { useEffect, useState } from 'react'
import {
  ApiError,
  getTranslatePrompts,
  translateScript,
  transliterateNative,
  synthTts,
  listTranslateVoices,
  getTranslationHistory,
  getTranslationHistoryItem,
  deleteTranslationHistory,
  type ProviderVoice,
  type TranslationHistoryItem,
  TRANSLATE_SOURCE_LANGUAGES,
  TRANSLATE_TARGET_LANGUAGES,
  TRANSLATE_MODELS,
  TTS_VOICE_MODELS,
  TTS_SPEEDS,
  TTS_EMOTIONS,
  SCRIPT_DEFAULT_MODEL,
  TTS_DEFAULT_MODEL,
} from '../api'
import { Spinner, ErrorNote, EmptyState } from '../components/ui'
import { friendlyDateTime } from '../format'

type Card = {
  roman: string
  native: string
  audioUrl: string | null
  romanDirty: boolean
  nativeLoading: boolean
  ttsLoading: boolean
  error: string
  warning: string
  castOpen: boolean
  provider: string
  voicePick: Record<string, string> // character -> voice_id
  genderPick: Record<string, string> // character -> 'male' | 'female' (filters the voice list)
  speed: string
  emotion: string
  ttsVoiceModel: string
}
const blankCard = (): Card => ({
  roman: '',
  native: '',
  audioUrl: null,
  romanDirty: false,
  nativeLoading: false,
  ttsLoading: false,
  error: '',
  warning: '',
  castOpen: false,
  provider: 'cartesia',
  voicePick: {},
  genderPick: {},
  speed: 'normal',
  emotion: '',
  ttsVoiceModel: 'sonic-3',
})

const errText = (e: unknown) =>
  e instanceof ApiError ? e.detail : (e as Error)?.message || 'Something went wrong'

/** Distinct speaker names, in first-seen order. Mirrors the backend _split_label: matches
 *  'Name says: ...' (any case) and 'Name: ...' (Title-Case/CAPS only, so a mid-sentence colon
 *  isn't a label), normalized (strip '*') so cast keys bind identically on both sides. */
function parseChars(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const line of (text || '').split('\n')) {
    const s = line.trim()
    const m =
      s.match(/^(.{1,40}?)\s+says\s*:\s*.+$/i) ||
      // Unicode-aware (matches Python's Unicode \w) so accented names like "José:" bind on both sides
      s.match(/^\*{0,2}\s*(\p{Lu}[\p{L}\p{N}.'-]*(?:\s+\p{Lu}[\p{L}\p{N}.'-]*){0,3})\*{0,2}\s*:\s*.+$/u)
    if (m) {
      const n = m[1].trim().replace(/^\*+|\*+$/g, '').trim()
      if (n && !seen.has(n.toLowerCase())) {
        seen.add(n.toLowerCase())
        out.push(n)
      }
    }
  }
  return out
}

const INPUT =
  'w-full resize-y rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-violet-500/50 focus:outline-none'
const SELECT =
  'rounded-lg border border-white/10 bg-zinc-950/60 px-2 py-1.5 text-sm text-zinc-100 focus:border-violet-500/50 focus:outline-none'
const LABEL = 'text-xs font-medium uppercase tracking-wide text-zinc-500'

function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select className={SELECT} value={value} onChange={(e) => onChange(e.target.value)}>
      {TRANSLATE_MODELS.map((m) => (
        <option key={m.id} value={m.id}>
          {m.label}
        </option>
      ))}
    </select>
  )
}

/** A small "⚙ prompt" toggle that opens the default prompt for per-run editing.
 *  `value === null` means "use the default"; any string is an ephemeral override. */
function PromptBox({
  label,
  value,
  defaultText,
  onChange,
  open,
  setOpen,
}: {
  label: string
  value: string | null
  defaultText: string
  onChange: (v: string | null) => void
  open: boolean
  setOpen: (v: boolean) => void
}) {
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs text-zinc-400 hover:text-zinc-200"
      >
        ⚙ {label} prompt{value !== null ? ' (edited)' : ''} {open ? '▴' : '▾'}
      </button>
      {open && (
        <div className="mt-2 space-y-1">
          <textarea
            value={value ?? defaultText}
            onChange={(e) => onChange(e.target.value)}
            rows={10}
            spellCheck={false}
            className={`${INPUT} font-mono text-[12px] leading-relaxed`}
            placeholder={defaultText ? '' : 'Loading default prompt…'}
          />
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-zinc-600">Edits apply to this run only — the saved prompt isn't changed.</span>
            {value !== null && (
              <button
                type="button"
                onClick={() => onChange(null)}
                className="text-zinc-400 hover:text-zinc-200"
              >
                Reset to default
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to the execCommand fallback (e.g. non-secure-origin http) */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

function CopyButton({ text, disabled }: { text: string; disabled?: boolean }) {
  const [state, setState] = useState<'' | 'ok' | 'fail'>('')
  return (
    <button
      type="button"
      disabled={disabled || !text}
      onClick={async () => {
        const ok = await copyText(text)
        setState(ok ? 'ok' : 'fail')
        setTimeout(() => setState(''), 1500)
      }}
      className="text-[11px] text-zinc-500 hover:text-zinc-300 disabled:opacity-40"
    >
      {state === 'ok' ? 'Copied ✓' : state === 'fail' ? 'Copy failed' : 'Copy'}
    </button>
  )
}

/** Normalize a provider gender field to 'male' | 'female' | '' — check female FIRST ('female'
 *  contains the substring 'male'). Cartesia uses masculine/feminine; ElevenLabs male/female/neutral. */
function voiceGender(g?: string): 'male' | 'female' | '' {
  const s = (g || '').toLowerCase()
  if (s.includes('female') || s.includes('feminine') || s.includes('woman')) return 'female'
  if (s.includes('male') || s.includes('masculine') || s.includes('man')) return 'male'
  return ''
}
const FEMALE_HINT =
  /\b(woman|women|girl|lady|mother|mom|mum|aunt|aunty|sister|daughter|wife|grandmother|granny|miss|mrs|ms|she|her|devi|amma|akka|didi|maa|bride)\b/i
const MALE_HINT =
  /\b(man|men|boy|father|dad|uncle|brother|son|husband|grandfather|grandpa|mr|sir|he|him|anna|bhai|raja|groom)\b/i
/** Best-guess gender for a character name/role; defaults to male when unknown (user can flip it). */
function guessGender(name: string): 'male' | 'female' {
  if (FEMALE_HINT.test(name)) return 'female'
  if (MALE_HINT.test(name)) return 'male'
  return 'male'
}

/** Per-character voice casting: pick a provider, then a gender + voice for each character.
 *  Voices are fetched per (provider, language) and the list is filtered to the chosen gender.
 *  Cartesia covers a subset of languages; ElevenLabs is the multilingual fallback. */
function VoiceCast({
  language,
  characters,
  provider,
  picks,
  genders,
  onProviderChange,
  onPick,
  onGender,
}: {
  language: string
  characters: string[]
  provider: string
  picks: Record<string, string>
  genders: Record<string, string>
  onProviderChange: (p: string) => void
  onPick: (character: string, voiceId: string) => void
  onGender: (character: string, gender: string) => void
}) {
  const [voices, setVoices] = useState<ProviderVoice[]>([])
  const [err, setErr] = useState('')
  const [loadedFor, setLoadedFor] = useState('')
  const key = `${provider}|${language}`
  const loading = loadedFor !== key // derived — avoids setState in the effect body
  const shown = loading ? [] : voices // don't show the previous provider/language's voices while loading

  useEffect(() => {
    let live = true
    listTranslateVoices(provider, language)
      .then((r) => {
        if (live) {
          setVoices(r.voices)
          setErr('')
        }
      })
      .catch((e) => {
        if (live) setErr(e instanceof ApiError ? e.detail : 'Could not load voices')
      })
      .finally(() => {
        if (live) setLoadedFor(`${provider}|${language}`)
      })
    return () => {
      live = false
    }
  }, [provider, language])

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-white/10 bg-zinc-950/40 p-3">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Provider</span>
        <select className={SELECT} value={provider} onChange={(e) => onProviderChange(e.target.value)}>
          <option value="cartesia">Cartesia</option>
          <option value="elevenlabs">ElevenLabs</option>
        </select>
        {loading && <Spinner className="h-3.5 w-3.5" />}
        <span className="text-[11px] text-zinc-600">{shown.length} voices</span>
      </div>
      {!loading && err && <div className="text-[11px] text-amber-300">{err}</div>}
      {!loading && !err && shown.length === 0 && provider === 'cartesia' && (
        <div className="text-[11px] text-amber-300">
          Cartesia has no voices for {language} — switch to ElevenLabs.
        </div>
      )}
      {characters.length ? (
        characters.map((ch) => {
          const g = genders[ch] || guessGender(ch)
          // show voices matching the chosen gender; keep unknown/neutral-gender voices visible
          const opts = shown.filter((v) => {
            const vg = voiceGender(v.gender)
            return !vg || vg === g
          })
          return (
            <div key={ch} className="flex items-center gap-2">
              <span className="w-24 shrink-0 truncate text-xs text-zinc-300" title={ch}>
                {ch}
              </span>
              <select
                className={`${SELECT} shrink-0`}
                value={g}
                onChange={(e) => onGender(ch, e.target.value)}
                title="Character gender — filters the voice list"
              >
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
              <select
                className={`${SELECT} min-w-0 flex-1`}
                value={picks[ch] || ''}
                onChange={(e) => onPick(ch, e.target.value)}
              >
                <option value="">— default (narrator) —</option>
                {opts.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.name || v.voice_id}
                    {v.gender ? ` (${v.gender})` : ''}
                  </option>
                ))}
              </select>
            </div>
          )
        })
      ) : (
        <div className="text-[11px] text-zinc-500">
          No named characters in this script — the whole block uses one voice.
        </div>
      )}
    </div>
  )
}

export default function Translations() {
  const [sourceText, setSourceText] = useState('')
  const [sourceLang, setSourceLang] = useState<string>('English')
  const [targets, setTargets] = useState<Set<string>>(new Set())

  const [scriptModel, setScriptModel] = useState(SCRIPT_DEFAULT_MODEL)
  const [ttsModel, setTtsModel] = useState(TTS_DEFAULT_MODEL)

  const [scriptPrompt, setScriptPrompt] = useState<string | null>(null)
  const [ttsPrompt, setTtsPrompt] = useState<string | null>(null)
  const [scriptOpen, setScriptOpen] = useState(false)
  const [ttsOpen, setTtsOpen] = useState(false)
  const [defaults, setDefaults] = useState<{ script: string; tts: string }>({ script: '', tts: '' })

  const [results, setResults] = useState<Record<string, Card>>({})
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState('')

  const [history, setHistory] = useState<TranslationHistoryItem[]>([])
  const loadHistory = () =>
    getTranslationHistory()
      .then((r) => setHistory(r.items))
      .catch(() => {})

  useEffect(() => {
    getTranslatePrompts()
      .then(setDefaults)
      .catch(() => setDefaults({ script: '', tts: '' }))
    loadHistory()
  }, [])

  const loadFromHistory = async (id: number) => {
    try {
      const d = await getTranslationHistoryItem(id)
      setSourceText(d.source_text)
      setSourceLang(d.source_language)
      setTargets(new Set(d.target_languages))
      // load the romanized translations; native is re-derived on "Update native" (label-free, aligned)
      setResults(
        Object.fromEntries(
          d.target_languages
            .filter((l) => d.results[l])
            .map((l) => [l, { ...blankCard(), roman: d.results[l].roman, native: '' }]),
        ),
      )
      setGenError('')
    } catch (e) {
      setGenError(errText(e))
    }
  }

  const removeFromHistory = async (id: number) => {
    if (!window.confirm('Delete this translation? It is removed for the whole team.')) return
    setHistory((h) => h.filter((x) => x.id !== id))
    try {
      await deleteTranslationHistory(id)
    } catch {
      loadHistory() // restore on failure
    }
  }

  const toggleTarget = (lang: string) =>
    setTargets((prev) => {
      const next = new Set(prev)
      if (next.has(lang)) next.delete(lang)
      else next.add(lang)
      return next
    })

  const patch = (lang: string, p: Partial<Card>) =>
    setResults((r) => ({ ...r, [lang]: { ...r[lang], ...p } }))

  const canGenerate = sourceText.trim().length > 0 && targets.size > 0 && !generating

  const generate = async () => {
    const tgts = [...targets]
    if (!sourceText.trim() || !tgts.length) return
    setGenError('')
    setGenerating(true)
    setResults(Object.fromEntries(tgts.map((l) => [l, blankCard()])))
    try {
      const r = await translateScript({
        source_text: sourceText,
        source_language: sourceLang,
        target_languages: tgts,
        model: scriptModel,
        rules_override: scriptPrompt ?? undefined,
      })
      const next: Record<string, Card> = {}
      for (const res of r.results) {
        next[res.language] = {
          ...blankCard(),
          roman: res.script_roman ?? '',
          native: '', // derived below — the LLM's script_native may not be line-aligned to roman,
          nativeLoading: !res.error && !!res.script_roman, // which would break per-character casting
          error: res.error ?? '',
        }
      }
      setResults(next)
      if (r.error) setGenError(r.error)
      loadHistory() // the backend just saved this run to the team-shared history
      // Derive a clean, label-free, line-aligned native per language (guarantees the per-character
      // voice mapping lines up; this is the same transliteration "Update native" runs).
      for (const lang of Object.keys(next)) {
        const card = next[lang]
        if (card.error || !card.roman) continue
        transliterateNative({
          language: lang,
          roman: card.roman,
          model: ttsModel,
          prompt_override: ttsPrompt ?? undefined,
        })
          .then((nr) => patch(lang, { native: nr.native, romanDirty: false, nativeLoading: false }))
          .catch((e) => patch(lang, { nativeLoading: false, error: errText(e) }))
      }
    } catch (e) {
      setGenError(errText(e))
      setResults({})
    } finally {
      setGenerating(false)
    }
  }

  const updateNative = async (lang: string) => {
    patch(lang, { nativeLoading: true, error: '' })
    try {
      const r = await transliterateNative({
        language: lang,
        roman: results[lang].roman,
        model: ttsModel,
        prompt_override: ttsPrompt ?? undefined,
      })
      patch(lang, { native: r.native, romanDirty: false, nativeLoading: false })
    } catch (e) {
      patch(lang, { nativeLoading: false, error: errText(e) })
    }
  }

  const playTts = async (lang: string) => {
    const c = results[lang]
    patch(lang, { ttsLoading: true, error: '', warning: '' })
    // cast keys come from the romanized labels; the backend maps them onto the label-free native
    // sentences by line position
    const voices: Record<string, { provider: string; voice_id: string }> = {}
    for (const ch of parseChars(c.roman)) {
      const vid = c.voicePick[ch]
      if (vid) voices[ch] = { provider: c.provider, voice_id: vid }
    }
    try {
      const r = await synthTts({
        language: lang,
        text: c.native,
        roman: c.roman,
        voices: Object.keys(voices).length ? voices : undefined,
        speed: c.speed && c.speed !== 'normal' ? c.speed : undefined,
        emotion: c.emotion || undefined,
        tts_model: c.ttsVoiceModel || undefined,
      })
      patch(lang, { audioUrl: r.audio_url, ttsLoading: false, warning: r.warning || '' })
    } catch (e) {
      patch(lang, { ttsLoading: false, error: errText(e) })
    }
  }

  // change the source language; drop it from targets if it was selected (can't translate to self)
  const onSourceLang = (l: string) => {
    setSourceLang(l)
    setTargets((prev) => {
      if (!prev.has(l)) return prev
      const next = new Set(prev)
      next.delete(l)
      return next
    })
  }

  const orderedTargets = TRANSLATE_TARGET_LANGUAGES.filter((l) => targets.has(l))
  const hasResults = orderedTargets.some((l) => results[l])

  const downloadAll = () => {
    // only the currently-selected, generated languages (not ones the user has since deselected)
    const payload = {
      source_language: sourceLang,
      source_text: sourceText,
      results: Object.fromEntries(
        orderedTargets
          .filter((l) => results[l])
          .map((l) => [l, { roman: results[l].roman, native: results[l].native }]),
      ),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `translations-${sourceLang.toLowerCase()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fade-in-up space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white">Translations</h1>
          <p className="text-sm text-zinc-500">
            Paste a script, pick target languages, get the Romanized script + native TTS — in real time.
          </p>
        </div>
        {hasResults && (
          <button
            type="button"
            onClick={downloadAll}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-sm font-medium text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          >
            Download all
          </button>
        )}
      </div>

      {/* ---- control bar ---- */}
      <div className="space-y-4 rounded-2xl border border-white/10 bg-zinc-900/80 p-5">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className={LABEL}>Source script</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-500">Source language</span>
              <select className={SELECT} value={sourceLang} onChange={(e) => onSourceLang(e.target.value)}>
                {TRANSLATE_SOURCE_LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <textarea
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            rows={7}
            placeholder="Paste the script here. Speaker labels like 'Robot says:' are preserved; English teaching lines stay in English."
            className={INPUT}
          />
        </div>

        <div className="space-y-1.5">
          <span className={LABEL}>Target languages</span>
          <div className="flex flex-wrap gap-2">
            {TRANSLATE_TARGET_LANGUAGES.map((lang) => {
              const isSource = lang === sourceLang
              const on = targets.has(lang)
              return (
                <button
                  key={lang}
                  type="button"
                  disabled={isSource}
                  onClick={() => toggleTarget(lang)}
                  className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                    isSource
                      ? 'cursor-not-allowed border-white/5 bg-white/5 text-zinc-600'
                      : on
                        ? 'border-violet-400/40 bg-violet-600/30 text-violet-100'
                        : 'border-white/10 bg-white/5 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {lang}
                </button>
              )
            })}
          </div>
        </div>

        {/* per-section model + prompt controls */}
        <div className="grid gap-4 border-t border-white/10 pt-4 lg:grid-cols-2">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className={LABEL}>Script — Romanized</span>
              <ModelSelect value={scriptModel} onChange={setScriptModel} />
            </div>
            <PromptBox
              label="Script"
              value={scriptPrompt}
              defaultText={defaults.script}
              onChange={setScriptPrompt}
              open={scriptOpen}
              setOpen={setScriptOpen}
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className={LABEL}>TTS — Native script</span>
              <ModelSelect value={ttsModel} onChange={setTtsModel} />
            </div>
            <PromptBox
              label="TTS"
              value={ttsPrompt}
              defaultText={defaults.tts}
              onChange={setTtsPrompt}
              open={ttsOpen}
              setOpen={setTtsOpen}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={!canGenerate}
            onClick={generate}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-60"
          >
            {generating && <Spinner className="h-4 w-4 text-white" />}
            {generating ? 'Translating…' : 'Generate'}
          </button>
          {targets.size > 0 && (
            <span className="text-xs text-zinc-500">
              {targets.size} language{targets.size > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {genError && <ErrorNote message={genError} />}

      {/* ---- results ---- */}
      {!hasResults && !generating ? (
        <EmptyState
          icon="🌐"
          title="No translations yet"
          hint="Paste a script above, choose your target languages, and hit Generate."
        />
      ) : (
        <div className="space-y-4">
          {orderedTargets.map((lang) => {
            const c = results[lang]
            if (!c) return null
            return (
              <div key={lang} className="rounded-xl border border-white/10 bg-zinc-900/60 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{lang}</span>
                  {generating && !c.roman && !c.error && <Spinner className="h-3.5 w-3.5" />}
                </div>

                {c.error ? (
                  <ErrorNote message={c.error} />
                ) : (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {/* Script (Romanized) */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className={LABEL}>Script — Romanized</span>
                        <CopyButton text={c.roman} />
                      </div>
                      <textarea
                        value={c.roman}
                        onChange={(e) => patch(lang, { roman: e.target.value, romanDirty: true })}
                        rows={6}
                        className={INPUT}
                      />
                    </div>

                    {/* TTS (Native) */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className={LABEL}>TTS — Native script</span>
                        <CopyButton text={c.native} />
                      </div>
                      <textarea
                        value={c.native}
                        onChange={(e) => patch(lang, { native: e.target.value })}
                        rows={6}
                        className={`${INPUT} ${c.romanDirty ? 'opacity-60' : ''}`}
                      />
                      <div className="text-[10px] text-zinc-600">
                        Spoken as one continuous flow — speaker labels are stripped, not voiced.
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          disabled={c.nativeLoading}
                          onClick={() => updateNative(lang)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-white/5 disabled:opacity-50"
                        >
                          {c.nativeLoading && <Spinner className="h-3 w-3" />}↻ Update native
                        </button>
                        <button
                          type="button"
                          disabled={c.ttsLoading || !c.native || c.romanDirty}
                          title={c.romanDirty ? 'Update native first' : undefined}
                          onClick={() => playTts(lang)}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
                        >
                          {c.ttsLoading && <Spinner className="h-3 w-3 text-white" />}▶ Generate &amp; play
                        </button>
                        {c.romanDirty && (
                          <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">
                            Romanized edited — update native first
                          </span>
                        )}
                      </div>
                      {c.warning && (
                        <div className="text-[11px] text-amber-300">{c.warning}</div>
                      )}
                      {/* delivery controls (Cartesia; ignored by ElevenLabs) */}
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[11px] text-zinc-500">Voice model</span>
                        <select
                          className={`${SELECT} py-1 text-xs`}
                          value={c.ttsVoiceModel}
                          onChange={(e) => patch(lang, { ttsVoiceModel: e.target.value })}
                        >
                          {TTS_VOICE_MODELS.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                        <span className="ml-1 text-[11px] text-zinc-500">Speed</span>
                        <select
                          className={`${SELECT} py-1 text-xs`}
                          value={c.speed}
                          onChange={(e) => patch(lang, { speed: e.target.value })}
                        >
                          {TTS_SPEEDS.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.label}
                            </option>
                          ))}
                        </select>
                        <span className="ml-1 text-[11px] text-zinc-500">Emotion</span>
                        <select
                          className={`${SELECT} py-1 text-xs`}
                          value={c.emotion}
                          onChange={(e) => patch(lang, { emotion: e.target.value })}
                        >
                          {TTS_EMOTIONS.map((em) => (
                            <option key={em.id} value={em.id}>
                              {em.label}
                            </option>
                          ))}
                        </select>
                        <span className="text-[10px] text-zinc-600">Cartesia only</span>
                      </div>
                      <div>
                        <button
                          type="button"
                          onClick={() => patch(lang, { castOpen: !c.castOpen })}
                          className="text-[11px] text-zinc-400 hover:text-zinc-200"
                        >
                          🎙 Cast voices ({parseChars(c.roman).length} character
                          {parseChars(c.roman).length === 1 ? '' : 's'}) {c.castOpen ? '▴' : '▾'}
                        </button>
                        {c.castOpen && (
                          <VoiceCast
                            language={lang}
                            characters={parseChars(c.roman)}
                            provider={c.provider}
                            picks={c.voicePick}
                            genders={c.genderPick}
                            onProviderChange={(p) => patch(lang, { provider: p, voicePick: {} })}
                            onPick={(ch, vid) =>
                              patch(lang, { voicePick: { ...c.voicePick, [ch]: vid } })
                            }
                            onGender={(ch, g) =>
                              patch(lang, {
                                genderPick: { ...c.genderPick, [ch]: g },
                                voicePick: { ...c.voicePick, [ch]: '' }, // clear stale opposite-gender pick
                              })
                            }
                          />
                        )}
                      </div>
                      {c.audioUrl && (
                        <audio
                          key={c.audioUrl}
                          controls
                          autoPlay
                          src={c.audioUrl}
                          onError={() => patch(lang, { error: 'Audio expired — regenerate.' })}
                          className="mt-1 h-9 w-full"
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ---- team-shared history ---- */}
      {history.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-zinc-300">
            History <span className="font-normal text-zinc-600">— saved &amp; shared with the team</span>
          </h2>
          <div className="divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10 bg-zinc-900/40">
            {history.map((h) => (
              <div key={h.id} className="flex items-start gap-3 px-4 py-2.5 hover:bg-white/5">
                <button
                  type="button"
                  onClick={() => loadFromHistory(h.id)}
                  className="min-w-0 flex-1 text-left"
                  title="Load into the workbench"
                >
                  <div className="truncate text-sm text-zinc-200">{h.source_text || '(empty)'}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-zinc-500">
                    <span className="text-zinc-400">{h.source_language}</span>
                    <span>→ {h.target_languages.join(', ')}</span>
                    <span>· {h.who || 'someone'}</span>
                    <span>· {friendlyDateTime(h.created_at)}</span>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => removeFromHistory(h.id)}
                  className="shrink-0 text-[11px] text-zinc-600 hover:text-red-300"
                  title="Delete (removes for everyone)"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

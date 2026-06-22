import { useEffect, useState } from 'react'
import {
  ApiError,
  getTranslatePrompts,
  translateScript,
  transliterateNative,
  synthTts,
  listTranslateVoices,
  type ProviderVoice,
  TRANSLATE_SOURCE_LANGUAGES,
  TRANSLATE_TARGET_LANGUAGES,
  TRANSLATE_MODELS,
  SCRIPT_DEFAULT_MODEL,
  TTS_DEFAULT_MODEL,
} from '../api'
import { Spinner, ErrorNote, EmptyState } from '../components/ui'

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
})

const errText = (e: unknown) =>
  e instanceof ApiError ? e.detail : (e as Error)?.message || 'Something went wrong'

/** Distinct 'Name says:' speakers, in first-seen order. Normalized to match the backend's
 *  parse_turns (which does .strip('*')), so cast keys bind the same way on both sides. */
function parseChars(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const line of (text || '').split('\n')) {
    const m = line.match(/^\s*(.+?)\s+says:/i)
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

/** Per-character voice casting: pick a provider, then a voice for each character.
 *  Voices are fetched per (provider, language). Cartesia covers a subset of languages
 *  (its model errors on unsupported ones); ElevenLabs is the multilingual fallback. */
function VoiceCast({
  language,
  characters,
  provider,
  picks,
  onProviderChange,
  onPick,
}: {
  language: string
  characters: string[]
  provider: string
  picks: Record<string, string>
  onProviderChange: (p: string) => void
  onPick: (character: string, voiceId: string) => void
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
        characters.map((ch) => (
          <div key={ch} className="flex items-center gap-2">
            <span className="w-24 shrink-0 truncate text-xs text-zinc-300" title={ch}>
              {ch}
            </span>
            <select
              className={`${SELECT} min-w-0 flex-1`}
              value={picks[ch] || ''}
              onChange={(e) => onPick(ch, e.target.value)}
            >
              <option value="">— default (narrator) —</option>
              {shown.map((v) => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.name || v.voice_id}
                  {v.gender ? ` (${v.gender})` : ''}
                </option>
              ))}
            </select>
          </div>
        ))
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

  useEffect(() => {
    getTranslatePrompts()
      .then(setDefaults)
      .catch(() => setDefaults({ script: '', tts: '' }))
  }, [])

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
          native: res.script_native ?? '',
          error: res.error ?? '',
        }
      }
      setResults(next)
      if (r.error) setGenError(r.error)
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
    // build the per-character voice map from the cast picks (keys = romanized labels; the backend
    // keeps those labels Latin in the native text, so they bind there)
    const voices: Record<string, { provider: string; voice_id: string }> = {}
    for (const ch of parseChars(c.roman || c.native)) {
      const vid = c.voicePick[ch]
      if (vid) voices[ch] = { provider: c.provider, voice_id: vid }
    }
    try {
      const r = await synthTts({
        language: lang,
        text: c.native,
        voices: Object.keys(voices).length ? voices : undefined,
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
                      <div>
                        <button
                          type="button"
                          onClick={() => patch(lang, { castOpen: !c.castOpen })}
                          className="text-[11px] text-zinc-400 hover:text-zinc-200"
                        >
                          🎙 Cast voices {c.castOpen ? '▴' : '▾'}
                        </button>
                        {c.castOpen && (
                          <VoiceCast
                            language={lang}
                            characters={parseChars(c.roman || c.native)}
                            provider={c.provider}
                            picks={c.voicePick}
                            onProviderChange={(p) => patch(lang, { provider: p, voicePick: {} })}
                            onPick={(ch, vid) =>
                              patch(lang, { voicePick: { ...c.voicePick, [ch]: vid } })
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
    </div>
  )
}

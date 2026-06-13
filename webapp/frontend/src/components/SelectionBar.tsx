import { Spinner } from './ui'

/**
 * Floating action bar shown while multi-selecting in the Library.
 * Dumb component — Library owns the selection set and the bulk calls.
 */
export default function SelectionBar({
  count,
  generateCount,
  localizeCount,
  busy,
  note,
  warning,
  onShortlist,
  onDismiss,
  onGenerate,
  onLocalize,
  onSelectAll,
  onClear,
}: {
  count: number
  /** selected ads that look generatable (client pre-filter; server re-checks) */
  generateCount: number
  /** selected ads with an English script — eligible for language replication */
  localizeCount: number
  busy: boolean
  note: string
  /** live heads-up that some selected ads are already in the pipeline */
  warning?: string
  onShortlist: () => void
  onDismiss: () => void
  onGenerate: () => void
  onLocalize: () => void
  onSelectAll: () => void
  onClear: () => void
}) {
  const btn =
    'rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40'
  return (
    <div className="fixed bottom-4 left-1/2 z-40 -translate-x-1/2">
      <div className="fade-in-up flex flex-col items-center gap-1.5">
        {warning && (
          <div className="max-w-md rounded-full border border-amber-400/30 bg-amber-500/15 px-3 py-1 text-center text-[11px] text-amber-200 shadow-lg">
            ⚠ {warning}
          </div>
        )}
        {note && (
          <div className="rounded-full border border-white/10 bg-zinc-900/95 px-3 py-1 text-[11px] text-zinc-300 shadow-lg">
            {note}
          </div>
        )}
        <div className="flex items-center gap-2 rounded-2xl border border-white/15 bg-zinc-900/95 px-4 py-2.5 shadow-2xl shadow-black/50 backdrop-blur">
          <span className="text-sm font-semibold text-white">
            {count} selected
          </span>
          {busy && <Spinner className="h-3.5 w-3.5" />}
          <span className="h-5 w-px bg-white/10" />
          <button
            onClick={onShortlist}
            disabled={busy || count === 0}
            className={`${btn} bg-amber-500/90 text-amber-950 hover:bg-amber-400`}
          >
            ⭐ Shortlist
          </button>
          <button
            onClick={onGenerate}
            disabled={busy || generateCount === 0}
            title={
              generateCount === 0
                ? 'None of the selected ads can be generated (already have docs, no media, or not Facebook)'
                : undefined
            }
            className={`${btn} bg-violet-600 text-white hover:bg-violet-500`}
          >
            ✨ Generate scripts{generateCount > 0 ? ` (${generateCount})` : ''}…
          </button>
          <button
            onClick={onLocalize}
            disabled={busy || localizeCount === 0}
            title={
              localizeCount === 0
                ? 'None of the selected ads has an English Supernova script yet'
                : undefined
            }
            className={`${btn} border border-violet-400/40 bg-violet-600/20 text-violet-200 hover:bg-violet-600/35`}
          >
            🌍 Localize{localizeCount > 0 ? ` (${localizeCount})` : ''}…
          </button>
          <button
            onClick={onDismiss}
            disabled={busy || count === 0}
            className={`${btn} border border-white/10 text-zinc-400 hover:bg-white/5 hover:text-zinc-200`}
          >
            ✕ Dismiss
          </button>
          <span className="h-5 w-px bg-white/10" />
          <button
            onClick={onSelectAll}
            disabled={busy}
            className="text-xs text-violet-300 hover:underline"
          >
            Select all loaded
          </button>
          <button
            onClick={onClear}
            disabled={busy}
            className="text-xs text-zinc-500 hover:underline"
          >
            Clear (Esc)
          </button>
        </div>
      </div>
    </div>
  )
}

import { useApp } from '../AppContext'

// Who to ping when the server is unreachable. Edit this if the operator changes.
const OPERATOR = 'Dheeresh'

/**
 * Full-screen overlay shown when the backend (the operator's Mac) can't be reached,
 * so a teammate sees a friendly "ping the operator" message instead of assuming the
 * tool is broken. Covers in-session drops; it clears itself the moment the server is
 * back (AppContext keeps polling).
 */
export default function ServerDownOverlay() {
  const { serverDown } = useApp()
  if (!serverDown) return null
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/95 p-6 backdrop-blur-sm">
      <div className="fade-in-up max-w-md text-center">
        <div className="text-5xl">😴</div>
        <h1 className="mt-4 text-xl font-semibold text-white">Ad Studio is offline</h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-400">
          The server that powers this — {OPERATOR}'s Mac — looks like it's asleep or
          disconnected right now. Nothing's broken; it'll come back on its own once the
          machine is online again.
        </p>
        <p className="mt-4 text-sm text-zinc-200">
          Please ping <span className="font-semibold text-white">{OPERATOR}</span> to bring it back.
        </p>
        <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-zinc-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
          Reconnecting automatically…
        </div>
      </div>
    </div>
  )
}

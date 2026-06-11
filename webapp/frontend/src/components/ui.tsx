import type { ReactNode } from 'react'
import { statusBadge, verdictBadge } from '../format'

export function VerdictBadge({ verdict }: { verdict: string }) {
  const b = verdictBadge(verdict)
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${b.className}`}
    >
      {b.label}
    </span>
  )
}

export function StatusChip({
  status,
  suffix,
}: {
  status: string
  suffix?: string
}) {
  const b = statusBadge(status)
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${b.className}`}
    >
      {b.label}
      {suffix ? <span className="font-normal opacity-80">— {suffix}</span> : null}
    </span>
  )
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin text-violet-400 ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
      />
    </svg>
  )
}

export function EmptyState({
  icon = '🌌',
  title,
  hint,
  children,
}: {
  icon?: string
  title: string
  hint?: string
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-white/10 bg-zinc-900/40 px-8 py-16 text-center">
      <div className="text-3xl">{icon}</div>
      <div className="text-base font-medium text-zinc-200">{title}</div>
      {hint && <div className="max-w-md text-sm text-zinc-500">{hint}</div>}
      {children}
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  )
}

export function PageLoading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-zinc-400">
      <Spinner className="h-5 w-5" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

/** Inline SVG sparkline of rank-over-time. Rank 1 is the TOP of the chart. */
export function RankSparkline({
  points,
  width = 280,
  height = 64,
}: {
  points: { date: string; rank: number }[]
  width?: number
  height?: number
}) {
  if (!points.length) {
    return <div className="text-xs text-zinc-500">No rank history yet</div>
  }
  const pad = 6
  const ranks = points.map((p) => p.rank)
  const min = Math.min(...ranks)
  const max = Math.max(...ranks)
  const span = Math.max(1, max - min)
  const x = (i: number) =>
    points.length === 1
      ? width / 2
      : pad + (i * (width - pad * 2)) / (points.length - 1)
  // rank 1 (best) at the top → low rank = low y
  const y = (r: number) => pad + ((r - min) / span) * (height - pad * 2)

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.rank).toFixed(1)}`)
    .join(' ')

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      className="block"
      role="img"
      aria-label="Rank over time (higher line = better rank)"
    >
      {points.length > 1 && (
        <path d={path} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" />
      )}
      {points.map((p, i) => (
        <circle
          key={`${p.date}-${i}`}
          cx={x(i)}
          cy={y(p.rank)}
          r={points.length === 1 ? 4 : 2.5}
          fill="#a78bfa"
        />
      ))}
    </svg>
  )
}

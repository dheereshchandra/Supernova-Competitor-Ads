import type { ReactNode } from 'react'
import { friendlyDate, statusBadge, verdictBadge } from '../format'

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

/** A small ⓘ dot that reveals a popover on hover/focus (full explanation). */
export function InfoDot({
  label = 'More info',
  children,
}: {
  label?: string
  children: ReactNode
}) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-white/20 text-[10px] font-semibold text-zinc-400 hover:border-violet-400/50 hover:text-violet-300"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-6 z-50 hidden w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-zinc-900 p-3 text-left text-[11px] leading-relaxed text-zinc-400 shadow-2xl group-hover:block group-focus-within:block"
      >
        {children}
      </span>
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

/** Rank-over-time chart. Best rank (lowest #) is at the TOP; a left Y-axis shows
 * the best/worst rank in the window, and the first & last points are labelled
 * with their rank so it's clear where the line sits. */
export function RankSparkline({
  points,
  width = 300,
  height = 104,
}: {
  points: { date: string; rank: number }[]
  width?: number
  height?: number
}) {
  if (!points.length) {
    return <div className="text-xs text-zinc-500">No rank history yet</div>
  }
  const ranks = points.map((p) => p.rank)
  const min = Math.min(...ranks) // best rank (smallest number)
  const max = Math.max(...ranks) // worst rank
  const flat = min === max
  const span = Math.max(1, max - min)
  const gutter = 40, rightPad = 24, topPad = 18, botPad = 16
  const pL = gutter, pR = width - rightPad, pT = topPad, pB = height - botPad
  const x = (i: number) =>
    points.length === 1 ? (pL + pR) / 2 : pL + (i * (pR - pL)) / (points.length - 1)
  const y = (r: number) => (flat ? (pT + pB) / 2 : pT + ((r - min) / span) * (pB - pT))
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.rank).toFixed(1)}`)
    .join(' ')
  const last = points[points.length - 1]

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block" role="img"
        aria-label="Rank over time — higher on the chart is a better rank">
        {/* y-axis */}
        <line x1={gutter} y1={pT - 4} x2={gutter} y2={pB + 4} stroke="#ffffff14" />
        {flat ? (
          <text x={gutter - 6} y={(pT + pB) / 2 + 3} textAnchor="end"
            className="fill-zinc-500" fontSize="10">#{min}</text>
        ) : (
          <>
            <text x={gutter - 6} y={pT + 3} textAnchor="end" className="fill-zinc-500" fontSize="10">#{min}</text>
            <text x={gutter - 6} y={pB + 3} textAnchor="end" className="fill-zinc-500" fontSize="10">#{max}</text>
          </>
        )}
        {points.length > 1 && (
          <path d={path} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" />
        )}
        {points.map((p, i) => (
          <circle key={`${p.date}-${i}`} cx={x(i)} cy={y(p.rank)} r={points.length === 1 ? 4 : 2.6} fill="#a78bfa" />
        ))}
        {/* label the first point (and the last, if different) with its rank */}
        <text x={x(0)} y={y(points[0].rank) - 7} textAnchor="middle"
          className="fill-violet-300 font-medium" fontSize="10">#{points[0].rank}</text>
        {points.length > 1 && (
          <text x={x(points.length - 1)} y={y(last.rank) - 7} textAnchor="middle"
            className="fill-violet-300 font-medium" fontSize="10">#{last.rank}</text>
        )}
      </svg>
      <div className="mt-1 flex items-center justify-between px-1 text-[10px] text-zinc-600">
        <span>{friendlyDate(points[0].date)}</span>
        <span className="text-zinc-500">↑ better rank</span>
        <span>{friendlyDate(last.date)}</span>
      </div>
    </div>
  )
}

// Display maps + friendly formatting. Plain English for a non-technical video team.

export interface BadgeStyle {
  label: string
  className: string
}

export const VERDICT_MAP: Record<string, BadgeStyle> = {
  strong_winner: {
    label: 'Top winner',
    className: 'bg-violet-500/20 text-violet-300 border border-violet-400/30',
  },
  winner: {
    label: 'Winner',
    className: 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30',
  },
  undecided: {
    label: 'Undecided',
    className: 'bg-zinc-500/20 text-zinc-300 border border-zinc-400/20',
  },
  new: {
    label: 'New',
    className: 'bg-sky-500/20 text-sky-300 border border-sky-400/30',
  },
  loser: {
    label: 'Underperformer',
    className: 'bg-red-500/15 text-red-300 border border-red-400/25',
  },
}

export function verdictBadge(verdict: string): BadgeStyle {
  return (
    VERDICT_MAP[verdict] ?? {
      label: verdict || 'Unknown',
      className: 'bg-zinc-500/20 text-zinc-300 border border-zinc-400/20',
    }
  )
}

export const STATUS_MAP: Record<string, BadgeStyle> = {
  shortlisted: {
    label: 'Shortlisted',
    className: 'bg-amber-500/20 text-amber-300 border border-amber-400/30',
  },
  generating: {
    label: 'Generating…',
    className:
      'bg-violet-500/20 text-violet-300 border border-violet-400/30 animate-pulse',
  },
  script_ready: {
    label: 'Script ready',
    className: 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30',
  },
  in_edit: {
    label: 'In edit',
    className: 'bg-sky-500/20 text-sky-300 border border-sky-400/30',
  },
  approved: {
    label: 'Approved',
    className: 'bg-green-500/20 text-green-300 border border-green-400/30',
  },
  in_production: {
    label: 'In production',
    className: 'bg-orange-500/20 text-orange-300 border border-orange-400/30',
  },
  shipped: {
    label: 'Shipped ✓',
    className: 'bg-zinc-500/20 text-zinc-300 border border-zinc-400/20',
  },
  dismissed: {
    label: 'Dismissed',
    className: 'bg-zinc-600/20 text-zinc-400 border border-zinc-500/20',
  },
  dropped: {
    label: 'Dropped',
    className: 'bg-zinc-600/20 text-zinc-400 border border-zinc-500/20',
  },
}

export function statusBadge(status: string): BadgeStyle {
  return (
    STATUS_MAP[status] ?? {
      label: status,
      className: 'bg-zinc-500/20 text-zinc-300 border border-zinc-400/20',
    }
  )
}

// The production flow, in order, for the board + the status stepper.
export const STATUS_FLOW = [
  'shortlisted',
  'generating',
  'script_ready',
  'in_edit',
  'approved',
  'in_production',
  'shipped',
] as const

export const JOB_STATUS_MAP: Record<string, BadgeStyle> = {
  queued: {
    label: 'Waiting in line',
    className: 'bg-zinc-500/20 text-zinc-300 border border-zinc-400/20',
  },
  running: {
    label: 'Generating…',
    className:
      'bg-violet-500/20 text-violet-300 border border-violet-400/30 animate-pulse',
  },
  interrupted: {
    label: 'Interrupted',
    className: 'bg-amber-500/20 text-amber-300 border border-amber-400/30',
  },
  awaiting_confirm: {
    label: 'Needs your OK',
    className: 'bg-amber-500/20 text-amber-200 border border-amber-400/40',
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-500/20 text-red-300 border border-red-400/30',
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-zinc-600/20 text-zinc-400 border border-zinc-500/20',
  },
  done: {
    label: 'Done ✓',
    className: 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30',
  },
}

// ---------- Dates & numbers ----------

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s.includes('T') || s.includes(' ') ? s.replace(' ', 'T') : `${s}T00:00:00`)
  return isNaN(d.getTime()) ? null : d
}

/** "Feb 19" or "Feb 19, 2025" when not this year. */
export function friendlyDate(s: string | null | undefined): string {
  const d = parseDate(s)
  if (!d) return '—'
  const now = new Date()
  const base = `${MONTHS[d.getMonth()]} ${d.getDate()}`
  return d.getFullYear() === now.getFullYear() ? base : `${base}, ${d.getFullYear()}`
}

/** "Jun 10, 8:29 PM" for timestamps. */
export function friendlyDateTime(s: string | null | undefined): string {
  const d = parseDate(s)
  if (!d) return '—'
  let h = d.getHours()
  const ampm = h >= 12 ? 'PM' : 'AM'
  h = h % 12 || 12
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${h}:${m} ${ampm}`
}

export function daysSince(s: string | null | undefined): number | null {
  const d = parseDate(s)
  if (!d) return null
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86_400_000))
}

/** "just now", "2h ago", "3 days ago" */
export function timeAgo(s: string | null | undefined): string {
  const d = parseDate(s)
  if (!d) return '—'
  const sec = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  const days = Math.floor(sec / 86400)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export function elapsedBetween(
  start: string | null | undefined,
  end?: string | null,
): string {
  const a = parseDate(start)
  if (!a) return '—'
  const b = end ? parseDate(end) : new Date()
  if (!b) return '—'
  const sec = Math.max(0, Math.floor((b.getTime() - a.getTime()) / 1000))
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  return `${Math.floor(min / 60)}h ${min % 60}m`
}

// Costs are computed in USD (Gemini billing) but the team thinks in rupees.
// The backend sends the conversion rate (STUDIO_USD_TO_INR) via /api/health;
// 95 is only the pre-fetch fallback.
let usdToInr = 95

export function setUsdToInr(rate: number | null | undefined): void {
  if (rate && rate > 0) usdToInr = rate
}

/** Format a USD-denominated cost as rupees, e.g. ₹1.14 (small) / ₹2,850. */
export function money(n: number | null | undefined): string {
  if (n == null) return '—'
  const inr = n * usdToInr
  return `₹${inr.toLocaleString('en-IN', {
    minimumFractionDigits: inr < 10 ? 2 : 0,
    maximumFractionDigits: inr < 10 ? 2 : 0,
  })}`
}

export function formatCount(n: number): string {
  return n.toLocaleString('en-US')
}

export function runDaysLabel(ad: {
  run_days: number
  run_days_is_lower_bound: boolean
}): string {
  return `${ad.run_days}${ad.run_days_is_lower_bound ? '+' : ''} days`
}

/** Page-size-aware rank label: "top 1%" on big pages, "#1 / 3" on tiny ones
 * (a percentile of a 3-ad page is noise). */
export function rankPctLabel(
  rank: number | null | undefined,
  pageCount: number | null | undefined,
): string {
  if (rank == null) return ''
  if (!pageCount) return `#${rank}`
  if (pageCount < 20) return `#${rank} / ${pageCount}`
  return `top ${Math.max(1, Math.round((rank / pageCount) * 100))}%`
}

export function domainOf(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

import type { AdGroup } from '../api'
import AdCard from './AdCard'

/**
 * A script-group tile: the representative ad's card with a stacked-cards
 * effect, an "N ads" badge and the languages the script was replicated into.
 * Clicking opens the variants drawer (Library passes the link).
 */
export default function GroupCard({
  group,
  to,
  rankPill,
}: {
  group: AdGroup
  to: string
  rankPill?: string
}) {
  const narrowed = group.members_matching < group.group_size_total
  const langs = group.languages.slice(0, 2)
  const moreLangs = group.languages_total - langs.length
  return (
    <div className="relative">
      {/* cards "behind" the representative — pure CSS stack */}
      <div className="absolute inset-x-2 -top-1.5 h-4 rounded-t-xl border border-white/10 bg-zinc-800/50" />
      <div className="absolute inset-x-1 -top-[3px] h-4 rounded-t-xl border border-white/10 bg-zinc-800/80" />
      <div className="relative">
        <AdCard
          ad={group.representative}
          to={to}
          rankPill={rankPill}
          topRight={
            <span className="rounded-full bg-violet-600/90 px-2 py-0.5 text-[10px] font-semibold text-white shadow">
              ⧉ {group.group_size_total} ads
            </span>
          }
          subtitle={
            <div className="flex h-[16px] items-center gap-1 overflow-hidden text-[10px]">
              {langs.map((l) => (
                <span
                  key={l}
                  className="shrink-0 rounded bg-white/10 px-1 py-px text-zinc-300"
                >
                  {l}
                </span>
              ))}
              {moreLangs > 0 && (
                <span className="shrink-0 text-zinc-500">+{moreLangs}</span>
              )}
              {narrowed && (
                <span className="truncate text-zinc-500">
                  · {group.members_matching} of {group.group_size_total} match
                </span>
              )}
            </div>
          }
        />
      </div>
    </div>
  )
}

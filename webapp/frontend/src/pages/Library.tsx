import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  getAds,
  getCompetitors,
  type Ad,
  type AdsResponse,
  type Competitor,
} from '../api'
import { useApp } from '../AppContext'
import { formatCount } from '../format'
import AdCard from '../components/AdCard'
import RunWorkflowModal from '../components/RunWorkflowModal'
import { EmptyState, ErrorNote, PageLoading, Spinner } from '../components/ui'

const PAGE_SIZE = 60
const NEW_DAYS = 7 // "newly added this week"

const SORTS = [
  { id: 'run_days', label: 'Longest running' },
  { id: 'best_page_rank', label: 'Best rank' },
  { id: 'first_seen', label: 'Newest' },
]

// Row-2 quick filters. `top`+`win` are on by default (the library opens on winners).
const QUICK = ['top', 'win', 'new', 'script', 'notrev'] as const
type Quick = (typeof QUICK)[number]
const DEFAULT_QUICK: Quick[] = ['top', 'win']

interface Filters {
  pipeline: string
  competitor: string
  language: string
  retired: 'any' | 'yes' | 'no'
  mediaType: '' | 'Video' | 'Image'
  sort: string
  q: string
  quick: Quick[]
}

function filtersFromParams(sp: URLSearchParams): Filters {
  return {
    pipeline: sp.get('pipeline') ?? 'facebook',
    competitor: sp.get('competitor') ?? '',
    language: sp.get('language') ?? '',
    retired: (sp.get('retired') as Filters['retired']) ?? 'any',
    mediaType: (sp.get('media') as Filters['mediaType']) ?? '',
    sort: sp.get('sort') ?? 'run_days',
    q: sp.get('q') ?? '',
    quick: sp.has('qf')
      ? (sp.get('qf')!.split(',').filter((x) => QUICK.includes(x as Quick)) as Quick[])
      : DEFAULT_QUICK,
  }
}

function paramsFromFilters(f: Filters): URLSearchParams {
  const sp = new URLSearchParams()
  if (f.pipeline !== 'facebook') sp.set('pipeline', f.pipeline)
  if (f.competitor) sp.set('competitor', f.competitor)
  if (f.language) sp.set('language', f.language)
  if (f.retired !== 'any') sp.set('retired', f.retired)
  if (f.mediaType) sp.set('media', f.mediaType)
  if (f.sort !== 'run_days') sp.set('sort', f.sort)
  if (f.q) sp.set('q', f.q)
  sp.set('qf', f.quick.join(',')) // always present so toggling all-off round-trips
  return sp
}

function buildQuery(f: Filters, page: number): URLSearchParams {
  const p = new URLSearchParams()
  p.set('pipeline', f.pipeline)
  if (f.competitor) p.set('competitor', f.competitor)
  const verdicts = [
    f.quick.includes('top') ? 'strong_winner' : '',
    f.quick.includes('win') ? 'winner' : '',
  ].filter(Boolean)
  if (verdicts.length) p.set('verdict', verdicts.join(','))
  if (f.quick.includes('new')) p.set('first_seen_days', String(NEW_DAYS))
  if (f.quick.includes('script')) p.set('generated', 'yes')
  if (f.quick.includes('notrev')) p.set('status', 'none')
  if (f.mediaType) p.set('media_type', f.mediaType)
  if (f.language) p.set('language', f.language)
  if (f.retired !== 'any') p.set('retired', f.retired)
  p.set('has_media', 'true')
  if (f.q.trim()) p.set('q', f.q.trim())
  p.set('sort', f.sort)
  p.set('order', f.sort === 'best_page_rank' ? 'asc' : 'desc')
  p.set('page', String(page))
  p.set('page_size', String(PAGE_SIZE))
  return p
}

const QUICK_LABELS: Record<Quick, string> = {
  top: '🏆 Top winners',
  win: '🥈 Winners',
  new: '🆕 Newly added this week',
  script: '📝 Has script ready',
  notrev: '👀 Not reviewed yet',
}

export default function Library() {
  const { noteDataAsOf, dataVersion, refreshActiveJobs } = useApp()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams])

  const [showRun, setShowRun] = useState(false)
  const [competitors, setCompetitors] = useState<Competitor[]>([])
  const [ads, setAds] = useState<Ad[]>([])
  const [total, setTotal] = useState(0)
  const [facets, setFacets] = useState<AdsResponse['facets'] | null>(null)
  const [newCount, setNewCount] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [searchText, setSearchText] = useState(filters.q)
  const fetchSeq = useRef(0)

  const updateFilters = useCallback(
    (patch: Partial<Filters>) => {
      setSearchParams(paramsFromFilters({ ...filters, ...patch }), { replace: false })
    },
    [filters, setSearchParams],
  )

  // competitors for the select + "new this week" count (re-fetch after a data run)
  useEffect(() => {
    getCompetitors()
      .then((r) => {
        setCompetitors(r.competitors ?? [])
        noteDataAsOf(r.data_as_of)
      })
      .catch(() => {})
  }, [noteDataAsOf, dataVersion])

  useEffect(() => {
    const p = new URLSearchParams({
      pipeline: filters.pipeline,
      first_seen_days: String(NEW_DAYS),
      has_media: 'true',
      page_size: '1',
    })
    if (filters.competitor) p.set('competitor', filters.competitor)
    getAds(p)
      .then((r) => setNewCount(r.total))
      .catch(() => setNewCount(null))
  }, [filters.pipeline, filters.competitor, dataVersion])

  // main fetch on filter change
  useEffect(() => {
    const seq = ++fetchSeq.current
    setLoading(true)
    setError('')
    setPage(1)
    getAds(buildQuery(filters, 1))
      .then((r) => {
        if (seq !== fetchSeq.current) return
        setAds(r.ads ?? [])
        setTotal(r.total ?? 0)
        setFacets(r.facets ?? null)
        noteDataAsOf(r.data_as_of)
      })
      .catch((e: Error) => {
        if (seq !== fetchSeq.current) return
        setError(e.message || 'Could not load ads')
        setAds([])
        setTotal(0)
      })
      .finally(() => {
        if (seq === fetchSeq.current) setLoading(false)
      })
  }, [filters, noteDataAsOf, dataVersion])

  const loadMore = () => {
    const nextPage = page + 1
    setLoadingMore(true)
    getAds(buildQuery(filters, nextPage))
      .then((r) => {
        setAds((prev) => [...prev, ...(r.ads ?? [])])
        setPage(nextPage)
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false))
  }

  useEffect(() => {
    setSearchText(filters.q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.pipeline, filters.competitor])
  const searchTimer = useRef<number | null>(null)
  const onSearch = (text: string) => {
    setSearchText(text)
    if (searchTimer.current) window.clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => updateFilters({ q: text }), 300)
  }

  const toggleQuick = (q: Quick) => {
    const next = filters.quick.includes(q)
      ? filters.quick.filter((x) => x !== q)
      : [...filters.quick, q]
    updateFilters({ quick: next })
  }

  const pipelineCompetitors = competitors.filter(
    (c) => !filters.pipeline || c.pipeline === filters.pipeline,
  )
  const languageFacet = facets?.language ?? {}
  const hasLanguages = Object.keys(languageFacet).length > 0
  const quickCount = (q: Quick): number | null => {
    if (q === 'top') return facets?.verdict?.strong_winner ?? null
    if (q === 'win') return facets?.verdict?.winner ?? null
    if (q === 'new') return newCount
    return null
  }

  const selectCls =
    'rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-200 outline-none focus:border-violet-400/50'

  return (
    <div className="space-y-4">
      {/* ---------- title + run-workflow ---------- */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Competitor ad library</h1>
          <p className="text-sm text-zinc-500">
            {formatCount(total)} ads · pick a winner to turn into a Supernova script
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {newCount != null && newCount > 0 && (
            <button
              onClick={() =>
                updateFilters({
                  quick: filters.quick.includes('new')
                    ? filters.quick
                    : [...filters.quick, 'new'],
                })
              }
              className="rounded-lg border border-sky-400/30 bg-sky-500/10 px-3 py-2 text-sm font-medium text-sky-200 transition-colors hover:bg-sky-500/20"
              title="Ads first seen in the last 7 days (from the daily 6 AM refresh)"
            >
              🆕 {formatCount(newCount)} new this week
            </button>
          )}
          <button
            onClick={() => setShowRun(true)}
            className="flex items-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/15 px-4 py-2 text-sm font-semibold text-violet-200 transition-colors hover:bg-violet-500/25"
            title="Scrape + refresh the latest data for a competitor"
          >
            ↻ Run data update
          </button>
        </div>
      </div>

      {/* ---------- sticky filter bar (3 stable rows) ---------- */}
      <div className="sticky top-14 z-30 -mx-6 space-y-3 border-b border-white/10 bg-zinc-950/95 px-6 py-3 backdrop-blur">
        {/* row 1: the dropdowns + toggles */}
        <div className="flex items-center gap-3">
          <select
            className={selectCls}
            value={filters.pipeline}
            onChange={(e) =>
              updateFilters({ pipeline: e.target.value, competitor: '', language: '' })
            }
            title="Ad platform"
          >
            <option value="facebook">Facebook</option>
            <option value="google">Google</option>
          </select>

          <select
            className={`${selectCls} w-[230px] truncate`}
            value={filters.competitor}
            onChange={(e) => updateFilters({ competitor: e.target.value })}
            title="Competitor"
          >
            <option value="">All competitors</option>
            {pipelineCompetitors.map((c) => {
              const w = c.by_verdict.strong_winner + c.by_verdict.winner
              return (
                <option key={`${c.pipeline}/${c.slug}`} value={c.slug}>
                  {c.page_name} ({w} winners)
                </option>
              )
            })}
          </select>

          <select
            className={`${selectCls} w-[150px]`}
            value={filters.language}
            onChange={(e) => updateFilters({ language: e.target.value })}
            title="Language"
            disabled={!hasLanguages}
          >
            <option value="">All languages</option>
            {Object.entries(languageFacet)
              .sort((a, b) => b[1] - a[1])
              .map(([lang, count]) => (
                <option key={lang} value={lang}>
                  {lang} ({formatCount(count)})
                </option>
              ))}
          </select>

          <Toggle
            value={filters.retired}
            onChange={(v) => updateFilters({ retired: v as Filters['retired'] })}
            options={[
              ['any', 'Any'],
              ['no', 'Live'],
              ['yes', 'Retired'],
            ]}
          />
          <Toggle
            value={filters.mediaType}
            onChange={(v) => updateFilters({ mediaType: v as Filters['mediaType'] })}
            options={[
              ['', 'Any'],
              ['Video', 'Video'],
              ['Image', 'Image'],
            ]}
          />

          <select
            className={`${selectCls} ml-auto w-[210px]`}
            value={filters.sort}
            onChange={(e) => updateFilters({ sort: e.target.value })}
            title="Order by"
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                Order by: {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* row 2: quick filters */}
        <div className="flex flex-wrap items-center gap-2">
          {QUICK.map((q) => {
            const on = filters.quick.includes(q)
            const count = quickCount(q)
            return (
              <button
                key={q}
                onClick={() => toggleQuick(q)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  on
                    ? 'border-violet-400/40 bg-violet-500/20 text-violet-100'
                    : 'border-white/10 text-zinc-400 hover:border-white/25 hover:text-zinc-200'
                }`}
              >
                {QUICK_LABELS[q]}
                {count != null && (
                  <span className="ml-1.5 tabular-nums opacity-70">{formatCount(count)}</span>
                )}
              </button>
            )
          })}
        </div>

        {/* row 3: search (also matches ad ID) */}
        <input
          type="search"
          placeholder="Search ad text or ad ID…"
          value={searchText}
          onChange={(e) => onSearch(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-violet-400/50"
        />
      </div>

      {/* ---------- grid ---------- */}
      {error ? (
        <ErrorNote message={error} />
      ) : loading ? (
        <PageLoading label="Loading the ad library…" />
      ) : ads.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="No ads match these filters"
          hint="Try widening the filters — turn on more quick filters or clear the search."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {ads.map((ad) => (
              <AdCard key={`${ad.pipeline}/${ad.competitor}/${ad.ad_id}`} ad={ad} />
            ))}
          </div>
          <div className="flex flex-col items-center gap-3 pt-2 pb-8">
            <span className="text-xs text-zinc-500">
              Showing {formatCount(ads.length)} of {formatCount(total)}
            </span>
            {ads.length < total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-6 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-violet-400/40 hover:text-white disabled:opacity-50"
              >
                {loadingMore && <Spinner className="h-4 w-4" />}
                Load {Math.min(PAGE_SIZE, total - ads.length)} more
              </button>
            )}
          </div>
        </>
      )}

      {showRun && (
        <RunWorkflowModal
          competitors={competitors}
          defaultPipeline={filters.pipeline}
          defaultCompetitor={filters.competitor}
          onClose={() => setShowRun(false)}
          onStarted={() => {
            setShowRun(false)
            refreshActiveJobs()
            navigate('/runs')
          }}
        />
      )}
    </div>
  )
}

function Toggle({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: readonly (readonly [string, string])[]
}) {
  return (
    <div className="flex shrink-0 overflow-hidden rounded-lg border border-white/10">
      {options.map(([val, label]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
            value === val
              ? 'bg-violet-500/25 text-violet-200'
              : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

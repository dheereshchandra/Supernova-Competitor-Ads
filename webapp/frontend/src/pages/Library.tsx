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
import { formatCount, parseDate, VERDICT_MAP } from '../format'
import AdCard from '../components/AdCard'
import RunWorkflowModal from '../components/RunWorkflowModal'
import { EmptyState, ErrorNote, PageLoading, Spinner } from '../components/ui'

const PAGE_SIZE = 60

type SmartView = 'winners' | 'new' | 'scripted' | 'unreviewed' | 'custom'

const SMART_VIEWS: { id: SmartView; label: string }[] = [
  { id: 'winners', label: '🏆 Proven winners' },
  { id: 'new', label: '🆕 New this week' },
  { id: 'scripted', label: '📝 Has script already' },
  { id: 'unreviewed', label: '👀 Not reviewed' },
]

const SORTS = [
  { id: 'run_days', label: 'Longest running' },
  { id: 'best_page_rank', label: 'Best rank' },
  { id: 'first_seen', label: 'Newest' },
]

const VERDICT_ORDER = ['strong_winner', 'winner', 'undecided', 'new', 'loser']

interface Filters {
  pipeline: string
  competitor: string
  verdicts: string[]
  mediaType: string
  language: string
  retired: 'any' | 'yes' | 'no'
  unprocessed: boolean
  generated: 'any' | 'yes'
  q: string
  sort: string
  view: SmartView
}

function filtersFromParams(sp: URLSearchParams): Filters {
  const view = (sp.get('view') as SmartView) || 'winners'
  const hasVerdictParam = sp.has('verdict')
  return {
    pipeline: sp.get('pipeline') ?? 'facebook',
    competitor: sp.get('competitor') ?? '',
    verdicts: hasVerdictParam
      ? sp.get('verdict')!.split(',').filter(Boolean)
      : view === 'new' || view === 'scripted'
        ? []
        : ['strong_winner', 'winner'],
    mediaType: sp.get('media_type') ?? '',
    language: sp.get('language') ?? '',
    retired: (sp.get('retired') as Filters['retired']) ?? 'any',
    unprocessed: sp.get('unprocessed') === '1' || view === 'unreviewed',
    generated: sp.get('generated') === 'yes' || view === 'scripted' ? 'yes' : 'any',
    q: sp.get('q') ?? '',
    sort: sp.get('sort') ?? (view === 'new' ? 'first_seen' : 'run_days'),
    view,
  }
}

function paramsFromFilters(f: Filters): URLSearchParams {
  const sp = new URLSearchParams()
  if (f.view !== 'winners') sp.set('view', f.view)
  if (f.pipeline !== 'facebook') sp.set('pipeline', f.pipeline)
  if (f.competitor) sp.set('competitor', f.competitor)
  sp.set('verdict', f.verdicts.join(','))
  if (f.mediaType) sp.set('media_type', f.mediaType)
  if (f.language) sp.set('language', f.language)
  if (f.retired !== 'any') sp.set('retired', f.retired)
  if (f.unprocessed) sp.set('unprocessed', '1')
  if (f.generated === 'yes') sp.set('generated', 'yes')
  if (f.q) sp.set('q', f.q)
  if (f.sort !== 'run_days') sp.set('sort', f.sort)
  return sp
}

function buildQuery(f: Filters, page: number): URLSearchParams {
  const p = new URLSearchParams()
  if (f.pipeline) p.set('pipeline', f.pipeline)
  if (f.competitor) p.set('competitor', f.competitor)
  if (f.verdicts.length) p.set('verdict', f.verdicts.join(','))
  if (f.mediaType) p.set('media_type', f.mediaType)
  if (f.language) p.set('language', f.language)
  if (f.retired !== 'any') p.set('retired', f.retired)
  if (f.unprocessed) p.set('status', 'none')
  if (f.generated === 'yes') p.set('generated', 'yes')
  p.set('has_media', 'true')
  if (f.q.trim()) p.set('q', f.q.trim())
  p.set('sort', f.sort)
  p.set('order', f.sort === 'best_page_rank' ? 'asc' : 'desc')
  p.set('page', String(page))
  p.set('page_size', String(PAGE_SIZE))
  return p
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
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [searchText, setSearchText] = useState(filters.q)
  const fetchSeq = useRef(0)

  // -------- competitors for the select (re-fetch when a data run finishes) --------
  useEffect(() => {
    getCompetitors()
      .then((r) => {
        setCompetitors(r.competitors ?? [])
        noteDataAsOf(r.data_as_of)
      })
      .catch(() => {})
  }, [noteDataAsOf, dataVersion])

  const updateFilters = useCallback(
    (patch: Partial<Filters>, toCustom = true) => {
      const next: Filters = { ...filters, ...patch }
      if (toCustom && patch.view === undefined) next.view = 'custom'
      setSearchParams(paramsFromFilters(next), { replace: false })
    },
    [filters, setSearchParams],
  )

  // -------- fetch ads on filter change --------
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

  // -------- debounced search --------
  useEffect(() => {
    setSearchText(filters.q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.view, filters.pipeline, filters.competitor])
  const searchTimer = useRef<number | null>(null)
  const onSearch = (text: string) => {
    setSearchText(text)
    if (searchTimer.current) window.clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => {
      updateFilters({ q: text })
    }, 300)
  }

  const applySmartView = (view: SmartView) => {
    if (view === 'winners') {
      updateFilters(
        {
          view,
          verdicts: ['strong_winner', 'winner'],
          unprocessed: false,
          generated: 'any',
          sort: 'run_days',
        },
        false,
      )
    } else if (view === 'new') {
      updateFilters(
        { view, verdicts: [], unprocessed: false, generated: 'any', sort: 'first_seen' },
        false,
      )
    } else if (view === 'scripted') {
      updateFilters(
        { view, verdicts: [], unprocessed: false, generated: 'yes', sort: 'run_days' },
        false,
      )
    } else if (view === 'unreviewed') {
      updateFilters(
        {
          view,
          verdicts: ['strong_winner', 'winner'],
          unprocessed: true,
          generated: 'any',
          sort: 'run_days',
        },
        false,
      )
    }
  }

  // "New this week" — client-side cut on first_seen within 7 days
  const visibleAds = useMemo(() => {
    if (filters.view !== 'new') return ads
    const cutoff = Date.now() - 7 * 86_400_000
    return ads.filter((a) => {
      const d = parseDate(a.first_seen)
      return d !== null && d.getTime() >= cutoff
    })
  }, [ads, filters.view])

  const toggleVerdict = (v: string) => {
    const has = filters.verdicts.includes(v)
    const next = has
      ? filters.verdicts.filter((x) => x !== v)
      : [...filters.verdicts, v]
    updateFilters({ verdicts: next })
  }

  const pipelineCompetitors = competitors.filter(
    (c) => !filters.pipeline || c.pipeline === filters.pipeline,
  )
  const languageFacet = facets?.language ?? {}
  const hasLanguages = Object.keys(languageFacet).length > 0
  const mediaTypes = Object.entries(facets?.media_type ?? {})

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
        <button
          onClick={() => setShowRun(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/15 px-4 py-2 text-sm font-semibold text-violet-200 transition-colors hover:bg-violet-500/25"
          title="Scrape + refresh the latest data for a competitor"
        >
          ↻ Run data update
        </button>
      </div>

      {/* ---------- sticky filter bar ---------- */}
      <div className="sticky top-14 z-30 -mx-6 border-b border-white/10 bg-zinc-950/95 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          {/* pipeline */}
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

          {/* competitor (fixed width so a longer name never shifts the row) */}
          <select
            className={`${selectCls} w-[230px] truncate`}
            value={filters.competitor}
            onChange={(e) => updateFilters({ competitor: e.target.value })}
            title="Competitor"
          >
            <option value="">All competitors</option>
            {pipelineCompetitors.map((c) => {
              const winners = c.by_verdict.strong_winner + c.by_verdict.winner
              return (
                <option key={`${c.pipeline}/${c.slug}`} value={c.slug}>
                  {c.page_name} ({winners} winners)
                </option>
              )
            })}
          </select>

          {/* language (always rendered so it never pops in/out) */}
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

          {/* live / retired */}
          <div className="flex overflow-hidden rounded-lg border border-white/10">
            {(
              [
                ['any', 'Any'],
                ['no', 'Live'],
                ['yes', 'Retired'],
              ] as const
            ).map(([val, label]) => (
              <button
                key={val}
                onClick={() => updateFilters({ retired: val })}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  filters.retired === val
                    ? 'bg-violet-500/25 text-violet-200'
                    : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* not yet processed */}
          <button
            onClick={() => updateFilters({ unprocessed: !filters.unprocessed })}
            className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
              filters.unprocessed
                ? 'border-amber-400/40 bg-amber-500/15 text-amber-200'
                : 'border-white/10 text-zinc-500 hover:border-white/25 hover:text-zinc-300'
            }`}
            title="Only show ads nobody has reviewed or scripted yet"
          >
            Not yet processed
          </button>
        </div>

        {/* row 2: verdict + media chips — isolated on their own row so their
            (count-driven) width can never shift the controls above */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {VERDICT_ORDER.map((v) => {
            const on = filters.verdicts.includes(v)
            const count = facets?.verdict?.[v]
            return (
              <button
                key={v}
                onClick={() => toggleVerdict(v)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  on
                    ? `${VERDICT_MAP[v].className}`
                    : 'border-white/10 text-zinc-500 hover:border-white/25 hover:text-zinc-300'
                }`}
              >
                {VERDICT_MAP[v].label}
                <span className="ml-1 inline-block min-w-[2ch] text-right tabular-nums opacity-70">
                  {count != null ? formatCount(count) : ''}
                </span>
              </button>
            )
          })}
          {mediaTypes.map(([mt, count]) => {
            const on = filters.mediaType === mt
            return (
              <button
                key={mt}
                onClick={() => updateFilters({ mediaType: on ? '' : mt })}
                className={`ml-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  on
                    ? 'border-violet-400/40 bg-violet-500/20 text-violet-200'
                    : 'border-white/10 text-zinc-500 hover:border-white/25 hover:text-zinc-300'
                }`}
              >
                {mt} <span className="tabular-nums opacity-60">{formatCount(count)}</span>
              </button>
            )
          })}
        </div>

        {/* row 3: search + sort on their own line so the filters never shift them */}
        <div className="mt-3 flex items-center gap-3">
          <input
            type="search"
            placeholder="Search ad text…"
            value={searchText}
            onChange={(e) => onSearch(e.target.value)}
            className="min-w-[180px] flex-1 rounded-lg border border-white/10 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-violet-400/50"
          />
          <select
            className={`${selectCls} w-[170px]`}
            value={filters.sort}
            onChange={(e) => updateFilters({ sort: e.target.value })}
            title="Sort order"
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ---------- smart views + count ---------- */}
      <div className="flex flex-wrap items-center gap-2">
        {SMART_VIEWS.map((sv) => (
          <button
            key={sv.id}
            onClick={() => applySmartView(sv.id)}
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
              filters.view === sv.id
                ? 'border-violet-400/40 bg-violet-500/20 text-violet-100'
                : 'border-white/10 bg-zinc-900/50 text-zinc-400 hover:border-white/25 hover:text-zinc-200'
            }`}
          >
            {sv.label}
          </button>
        ))}
        <span className="ml-auto text-sm text-zinc-500">
          {loading ? (
            'Loading…'
          ) : (
            <>
              <span className="font-semibold text-zinc-200">{formatCount(total)}</span>{' '}
              {filters.view === 'winners' ? 'winning ads' : 'ads'}
              {filters.view === 'new' && visibleAds.length !== ads.length
                ? ` · ${visibleAds.length} first seen this week`
                : ''}
            </>
          )}
        </span>
      </div>

      {/* ---------- grid ---------- */}
      {error ? (
        <ErrorNote message={error} />
      ) : loading ? (
        <PageLoading label="Loading the ad library…" />
      ) : visibleAds.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="No ads match these filters"
          hint={
            filters.view === 'new'
              ? 'Nothing new was spotted in the last 7 days. Try another view.'
              : 'Try widening the filters — switch verdicts back on or clear the search.'
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {visibleAds.map((ad) => (
              <AdCard key={`${ad.pipeline}/${ad.competitor}/${ad.ad_id}`} ad={ad} />
            ))}
          </div>
          {ads.length < total && filters.view !== 'new' && (
            <div className="flex justify-center pt-2 pb-8">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-6 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-violet-400/40 hover:text-white disabled:opacity-50"
              >
                {loadingMore && <Spinner className="h-4 w-4" />}
                Load more ({formatCount(total - ads.length)} remaining)
              </button>
            </div>
          )}
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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  adRef,
  bulkPatchTracker,
  getAds,
  getCompetitors,
  getPipelinePending,
  type Ad,
  type AdGroup,
  type AdsResponse,
  type Competitor,
} from '../api'
import { useApp } from '../AppContext'
import { formatCount, rankPctLabel } from '../format'
import AdCard from '../components/AdCard'
import BulkGenerateModal from '../components/BulkGenerateModal'
import BulkLocalizeModal from '../components/BulkLocalizeModal'
import GroupCard from '../components/GroupCard'
import GroupDrawer from '../components/GroupDrawer'
import RunWorkflowModal from '../components/RunWorkflowModal'
import SelectionBar from '../components/SelectionBar'
import { EmptyState, ErrorNote, InfoDot, PageLoading, Spinner } from '../components/ui'

const adKey = (a: Ad) => `${a.pipeline}/${a.competitor}/${a.ad_id}`

const PAGE_SIZE = 60
const NEW_DAYS = 7 // "newly added this week"

const SORTS = [
  { id: 'run_days', label: 'Longest running' },
  { id: 'rank_pct', label: 'Best rank (page-adjusted)' },
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
  fbpage: string
  platformOs: '' | 'iOS' | 'Android'
  retired: 'any' | 'yes' | 'no'
  mediaType: '' | 'Video' | 'Image'
  grouped: boolean
  sort: string
  q: string
  quick: Quick[]
}

function filtersFromParams(sp: URLSearchParams): Filters {
  const sort = sp.get('sort') ?? 'run_days'
  return {
    pipeline: sp.get('pipeline') ?? 'facebook',
    competitor: sp.get('competitor') ?? '',
    language: sp.get('language') ?? '',
    fbpage: sp.get('fbpage') ?? '',
    platformOs: (sp.get('os') as Filters['platformOs']) ?? '',
    retired: (sp.get('retired') as Filters['retired']) ?? 'any',
    mediaType: (sp.get('media') as Filters['mediaType']) ?? '',
    grouped: sp.get('group') !== 'none', // grouped is the default view
    sort: sort === 'best_page_rank' ? 'rank_pct' : sort, // old links → page-adjusted
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
  if (f.fbpage) sp.set('fbpage', f.fbpage)
  if (f.platformOs) sp.set('os', f.platformOs)
  if (f.retired !== 'any') sp.set('retired', f.retired)
  if (f.mediaType) sp.set('media', f.mediaType)
  if (!f.grouped) sp.set('group', 'none')
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
  if (f.fbpage) p.set('page_name', f.fbpage)
  if (f.platformOs) p.set('platform_os', f.platformOs)
  if (f.retired !== 'any') p.set('retired', f.retired)
  if (f.grouped) p.set('group', 'script')
  p.set('has_media', 'true')
  if (f.q.trim()) p.set('q', f.q.trim())
  p.set('sort', f.sort)
  p.set('order', f.sort === 'rank_pct' || f.sort === 'best_page_rank' ? 'asc' : 'desc')
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
  // The drawer param (`g`) lives in the URL too — exclude it from the key that
  // drives data fetches so opening/closing the drawer never refetches the grid.
  const filtersKey = useMemo(() => paramsFromFilters(filters).toString(), [filters])
  const drawerTarget = searchParams.get('g') // "<competitor>::<gid>"

  const [showRun, setShowRun] = useState(false)
  const [competitors, setCompetitors] = useState<Competitor[]>([])
  const [ads, setAds] = useState<Ad[]>([])
  const [groups, setGroups] = useState<AdGroup[] | null>(null)
  const [total, setTotal] = useState(0)
  const [totalAds, setTotalAds] = useState<number | null>(null)
  const [ungroupedAds, setUngroupedAds] = useState<number | null>(null)
  const [facets, setFacets] = useState<AdsResponse['facets'] | null>(null)
  const [osCoverage, setOsCoverage] = useState<AdsResponse['os_coverage'] | null>(null)
  const [newCount, setNewCount] = useState<number | null>(null)
  const [pendingCount, setPendingCount] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [searchText, setSearchText] = useState(filters.q)
  const [refreshTick, setRefreshTick] = useState(0)
  const fetchSeq = useRef(0)

  // multi-select (bulk shortlist / generate / dismiss)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [showBulkGen, setShowBulkGen] = useState(false)
  const [showBulkLocalize, setShowBulkLocalize] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkNote, setBulkNote] = useState('')
  const lastIndexRef = useRef<number | null>(null)

  const updateFilters = useCallback(
    (patch: Partial<Filters>) => {
      setSearchParams(paramsFromFilters({ ...filters, ...patch }), { replace: false })
      // the selection points at tiles that may no longer be visible — drop it
      setSelected(new Set())
      setSelectMode(false)
      setBulkNote('')
      lastIndexRef.current = null
    },
    [filters, setSearchParams],
  )

  const openDrawer = useCallback(
    (g: AdGroup) => {
      const sp = new URLSearchParams(searchParams)
      sp.set('g', `${g.representative.competitor}::${g.script_group_id}`)
      return `?${sp.toString()}`
    },
    [searchParams],
  )
  const closeDrawer = useCallback(() => {
    const sp = new URLSearchParams(searchParams)
    sp.delete('g')
    setSearchParams(sp, { replace: false })
  }, [searchParams, setSearchParams])

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

  // ads pending enrichment (the actionable backlog shown by the button)
  useEffect(() => {
    getPipelinePending(filters.pipeline)
      .then((p) => setPendingCount(p.total))
      .catch(() => setPendingCount(null))
  }, [filters.pipeline, dataVersion])

  // main fetch on filter change (keyed on filtersKey, NOT the filters object —
  // the drawer param recreates `filters` without changing anything meaningful)
  useEffect(() => {
    const seq = ++fetchSeq.current
    setLoading(true)
    setError('')
    setPage(1)
    getAds(buildQuery(filters, 1))
      .then((r) => {
        if (seq !== fetchSeq.current) return
        setAds(r.ads ?? [])
        setGroups(r.groups ?? null)
        setTotal(r.total ?? 0)
        setTotalAds(r.total_ads ?? null)
        setUngroupedAds(r.ungrouped_ads ?? null)
        setFacets(r.facets ?? null)
        setOsCoverage(r.os_coverage ?? null)
        noteDataAsOf(r.data_as_of)
      })
      .catch((e: Error) => {
        if (seq !== fetchSeq.current) return
        setError(e.message || 'Could not load ads')
        setAds([])
        setGroups(null)
        setTotal(0)
      })
      .finally(() => {
        if (seq === fetchSeq.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersKey, noteDataAsOf, dataVersion, refreshTick])

  const loadMore = () => {
    const nextPage = page + 1
    setLoadingMore(true)
    getAds(buildQuery(filters, nextPage))
      .then((r) => {
        setAds((prev) => [...prev, ...(r.ads ?? [])])
        if (r.groups) setGroups((prev) => [...(prev ?? []), ...r.groups!])
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

  // ---------- multi-select ----------

  // What the grid currently shows, one Ad per tile (group tiles contribute
  // their representative — one script per group is the point of dedup).
  const tiles: Ad[] = useMemo(
    () => (filters.grouped && groups ? groups.map((g) => g.representative) : ads),
    [filters.grouped, groups, ads],
  )
  const selectedAds = useMemo(
    () => tiles.filter((a) => selected.has(adKey(a))),
    [tiles, selected],
  )
  // client pre-filter for the Generate button; the server re-checks everything
  const generatableAds = useMemo(
    () =>
      selectedAds.filter(
        (a) =>
          a.pipeline === 'facebook' &&
          a.media_url &&
          !a.has_docs &&
          !a.has_gdocs &&
          !(a.job && (a.job.status === 'queued' || a.job.status === 'running')),
      ),
    [selectedAds],
  )
  // client pre-filter for the Localize button: needs an English Supernova script
  const localizableAds = useMemo(
    () =>
      selectedAds.filter(
        (a) =>
          a.pipeline === 'facebook' &&
          (a.rewrite_gdoc_url || a.has_gdocs) &&
          !(a.job && (a.job.status === 'queued' || a.job.status === 'running')),
      ),
    [selectedAds],
  )

  const toggleSelect = (ad: Ad, shiftKey: boolean) => {
    const idx = tiles.findIndex((a) => adKey(a) === adKey(ad))
    setSelected((prev) => {
      const next = new Set(prev)
      if (shiftKey && lastIndexRef.current != null && idx >= 0) {
        const lo = Math.min(lastIndexRef.current, idx)
        const hi = Math.max(lastIndexRef.current, idx)
        for (let i = lo; i <= hi; i++) next.add(adKey(tiles[i]))
      } else if (next.has(adKey(ad))) {
        next.delete(adKey(ad))
      } else {
        next.add(adKey(ad))
      }
      return next
    })
    if (idx >= 0) lastIndexRef.current = idx
    setSelectMode(true)
    setBulkNote('')
  }

  const clearSelection = () => {
    setSelected(new Set())
    setSelectMode(false)
    setBulkNote('')
    lastIndexRef.current = null
  }

  // Esc clears the selection — unless the drawer is open (it owns Esc then)
  useEffect(() => {
    if (drawerTarget) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelected(new Set())
        setSelectMode(false)
        setBulkNote('')
        lastIndexRef.current = null
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerTarget])

  const applyBulkStatus = async (status: 'shortlisted' | 'dismissed') => {
    if (selectedAds.length === 0) return
    setBulkBusy(true)
    setBulkNote('')
    try {
      const r = await bulkPatchTracker(selectedAds.map(adRef), status)
      // flip statuses in place — no refetch, so the grid doesn't reflow
      const targeted = new Set(selectedAds.map(adKey))
      const skipped = new Set(
        r.skipped.map((s) => `${s.pipeline}/${s.competitor}/${s.ad_id}`),
      )
      const flip = (a: Ad): Ad =>
        targeted.has(adKey(a)) && !skipped.has(adKey(a)) ? { ...a, status } : a
      setAds((prev) => prev.map(flip))
      setGroups((prev) =>
        prev
          ? prev.map((g) => ({ ...g, representative: flip(g.representative) }))
          : prev,
      )
      const verb = status === 'shortlisted' ? 'Shortlisted' : 'Dismissed'
      setBulkNote(
        `${verb} ${r.changed}` +
          (r.unchanged ? ` · ${r.unchanged} already were` : '') +
          (r.skipped.length ? ` · ${r.skipped.length} skipped (already in the flow)` : ''),
      )
      setSelected(new Set())
    } catch (e) {
      setBulkNote((e as Error).message || 'Something went wrong')
    } finally {
      setBulkBusy(false)
    }
  }

  const pipelineCompetitors = competitors.filter(
    (c) => !filters.pipeline || c.pipeline === filters.pipeline,
  )
  const languageFacet = facets?.language ?? {}
  const hasLanguages = Object.keys(languageFacet).length > 0
  // page facet only exists when a single competitor is selected (backend rule)
  const pageFacet = Object.entries(facets?.page ?? {}).sort((a, b) => b[1] - a[1])
  const grouped = filters.grouped
  const showEnrichBanner =
    grouped &&
    ungroupedAds != null &&
    totalAds != null &&
    totalAds > 0 &&
    ungroupedAds / totalAds > 0.05
  // OS is inferred from the destination link → only some ads can be classified.
  const osTotal = osCoverage?.total ?? 0
  const osKnown = osCoverage?.known ?? 0
  const osPct = osTotal ? Math.round((osKnown / osTotal) * 100) : 0
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
            {grouped && totalAds != null
              ? `${formatCount(total)} scripts · ${formatCount(totalAds)} ads · pick a winner to turn into a Supernova script`
              : `${formatCount(total)} ads · pick a winner to turn into a Supernova script`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <button
            onClick={() => (selectMode ? clearSelection() : setSelectMode(true))}
            className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              selectMode
                ? 'border-violet-400/40 bg-violet-500/20 text-violet-100'
                : 'border-white/10 text-zinc-400 hover:border-white/25 hover:text-zinc-200'
            }`}
            title="Select several ads, then shortlist or generate scripts in one go"
          >
            {selectMode ? 'Done selecting' : '☑ Select'}
          </button>
          {pendingCount != null && pendingCount > 0 && (
            <button
              onClick={() => setShowRun(true)}
              className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/20"
              title="Scraped ads not yet enriched (transcripts, language, format). Click to enrich."
            >
              ⏳ {formatCount(pendingCount)} pending enrichment
            </button>
          )}
          <button
            onClick={() => setShowRun(true)}
            className="flex items-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/15 px-4 py-2 text-sm font-semibold text-violet-200 transition-colors hover:bg-violet-500/25"
            title="Scrape + enrich the latest data for one or more competitors"
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
              updateFilters({
                pipeline: e.target.value,
                competitor: '',
                language: '',
                fbpage: '',
              })
            }
            title="Ad platform"
          >
            <option value="facebook">Facebook</option>
            <option value="google">Google</option>
          </select>

          <select
            className={`${selectCls} w-[230px] truncate`}
            value={filters.competitor}
            onChange={(e) => updateFilters({ competitor: e.target.value, fbpage: '' })}
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

          {filters.competitor && pageFacet.length >= 2 && (
            <select
              className={`${selectCls} w-[200px] truncate`}
              value={filters.fbpage}
              onChange={(e) => updateFilters({ fbpage: e.target.value })}
              title="This competitor runs ads from several Facebook pages — ranks are only comparable within one page"
            >
              <option value="">All pages ({pageFacet.length})</option>
              {pageFacet.map(([name, count]) => (
                <option key={name} value={name}>
                  {name} ({formatCount(count)} ads)
                </option>
              ))}
            </select>
          )}

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
          <Toggle
            value={grouped ? 'on' : 'off'}
            onChange={(v) => updateFilters({ grouped: v === 'on' })}
            options={[
              ['on', 'Grouped'],
              ['off', 'All ads'],
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

          {/* OS filter — last control so the ⓘ sits right after "Android",
              clearly belonging to this toggle (not the sort dropdown).
              OS is derived from the destination link; only some ads classify. */}
          <div className="flex items-center gap-1">
            <Toggle
              value={filters.platformOs}
              onChange={(v) => updateFilters({ platformOs: v as Filters['platformOs'] })}
              options={[
                ['', 'All platforms'],
                ['iOS', 'iOS'],
                ['Android', 'Android'],
              ]}
            />
            <InfoDot label="How the OS filter works">
              <p className="font-medium text-zinc-200">Operating-system filter</p>
              <p className="mt-1">
                Meta's Ad Library doesn't publish OS targeting, so we infer it from
                each ad's destination link — only a direct App Store / Play Store link
                is unambiguous.
              </p>
              {osTotal > 0 && (
                <p className="mt-2 text-zinc-300">
                  In this view: <b>{osPct}%</b> have a recognizable OS
                  {' '}({formatCount(osKnown)} of {formatCount(osTotal)}) —
                  iOS {formatCount(osCoverage?.ios ?? 0)} ·
                  Android {formatCount(osCoverage?.android ?? 0)}.
                </p>
              )}
              <p className="mt-2 text-zinc-500">
                The rest point to OS-agnostic web pages / lead forms, so they show only
                under “All platforms.” Use iOS/Android only when you specifically want
                that store's ads.
              </p>
            </InfoDot>
          </div>
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

      {/* ---------- enrichment-coverage note (grouped mode) ---------- */}
      {showEnrichBanner && !loading && !error && (
        <p className="text-xs text-zinc-600">
          Variant grouping uses transcripts — {formatCount(ungroupedAds!)} of{' '}
          {formatCount(totalAds!)} matching ads aren't transcribed yet and show
          individually.{' '}
          <button
            onClick={() => setShowRun(true)}
            className="text-violet-400/80 hover:underline"
          >
            Run enrichment →
          </button>
        </p>
      )}

      {/* ---------- grid ---------- */}
      {error ? (
        <ErrorNote message={error} />
      ) : loading ? (
        <PageLoading label="Loading the ad library…" />
      ) : (grouped && groups ? groups.length : ads.length) === 0 ? (
        <EmptyState
          icon="🔍"
          title="No ads match these filters"
          hint="Try widening the filters — turn on more quick filters or clear the search."
        />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7">
            {grouped && groups
              ? groups.map((g) => {
                  const rep = g.representative
                  const key = g.script_group_id || adKey(rep)
                  const pill =
                    filters.sort === 'rank_pct'
                      ? rankPctLabel(rep.best_page_rank, rep.page_count)
                      : undefined
                  return g.group_size_total > 1 ? (
                    <GroupCard
                      key={key}
                      group={g}
                      to={openDrawer(g)}
                      rankPill={pill}
                      selectMode={selectMode}
                      selected={selected.has(adKey(rep))}
                      onToggleSelect={toggleSelect}
                    />
                  ) : (
                    <AdCard
                      key={key}
                      ad={rep}
                      rankPill={pill}
                      selectMode={selectMode}
                      selected={selected.has(adKey(rep))}
                      onToggleSelect={toggleSelect}
                    />
                  )
                })
              : ads.map((ad) => (
                  <AdCard
                    key={adKey(ad)}
                    ad={ad}
                    rankPill={
                      filters.sort === 'rank_pct'
                        ? rankPctLabel(ad.best_page_rank, ad.page_count)
                        : undefined
                    }
                    selectMode={selectMode}
                    selected={selected.has(adKey(ad))}
                    onToggleSelect={toggleSelect}
                  />
                ))}
          </div>
          <div className="flex flex-col items-center gap-3 pt-2 pb-8">
            <span className="text-xs text-zinc-500">
              Showing {formatCount(grouped && groups ? groups.length : ads.length)} of{' '}
              {formatCount(total)}
              {grouped ? ' scripts' : ''}
            </span>
            {(grouped && groups ? groups.length : ads.length) < total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-6 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-violet-400/40 hover:text-white disabled:opacity-50"
              >
                {loadingMore && <Spinner className="h-4 w-4" />}
                Load{' '}
                {Math.min(
                  PAGE_SIZE,
                  total - (grouped && groups ? groups.length : ads.length),
                )}{' '}
                more
              </button>
            )}
          </div>
        </>
      )}

      {/* ---------- script-group drawer (deep-linkable via ?g=) ---------- */}
      {drawerTarget && drawerTarget.includes('::') && (
        <GroupDrawer
          key={drawerTarget}
          pipeline={filters.pipeline}
          competitor={drawerTarget.split('::')[0]}
          gid={drawerTarget.split('::').slice(1).join('::')}
          onClose={closeDrawer}
        />
      )}

      {/* ---------- multi-select action bar + bulk generate / localize ---------- */}
      {(selectMode || selected.size > 0) && !showBulkGen && !showBulkLocalize && (
        <SelectionBar
          count={selected.size}
          generateCount={generatableAds.length}
          localizeCount={localizableAds.length}
          busy={bulkBusy}
          note={bulkNote}
          onShortlist={() => applyBulkStatus('shortlisted')}
          onDismiss={() => applyBulkStatus('dismissed')}
          onGenerate={() => setShowBulkGen(true)}
          onLocalize={() => setShowBulkLocalize(true)}
          onSelectAll={() => setSelected(new Set(tiles.map(adKey)))}
          onClear={clearSelection}
        />
      )}
      {showBulkGen && (
        <BulkGenerateModal
          ads={generatableAds}
          onClose={() => setShowBulkGen(false)}
          onStarted={(queued) => {
            setShowBulkGen(false)
            clearSelection()
            refreshActiveJobs()
            if (queued > 0) setRefreshTick((t) => t + 1) // re-fetch → "Generating…" chips
          }}
        />
      )}
      {showBulkLocalize && (
        <BulkLocalizeModal
          ads={localizableAds}
          onClose={() => setShowBulkLocalize(false)}
          onStarted={(queued) => {
            setShowBulkLocalize(false)
            clearSelection()
            refreshActiveJobs()
            if (queued > 0) setRefreshTick((t) => t + 1)
          }}
        />
      )}

      {showRun && (
        <RunWorkflowModal
          competitors={competitors}
          defaultPipeline={filters.pipeline}
          defaultCompetitor={filters.competitor}
          onClose={() => setShowRun(false)}
          onStarted={(jobIds) => {
            setShowRun(false)
            refreshActiveJobs()
            if (jobIds.length) navigate('/runs')
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

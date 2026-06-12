// Typed fetch wrapper + API types for Supernova Ad Studio.
// All requests go to the same origin (/api/*) — Vite proxies in dev,
// FastAPI serves the bundle in production. Cookies do the auth work.

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

let authDisabled = false
export function setAuthDisabled(v: boolean) {
  authDisabled = v
}

export async function api<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const { json, ...rest } = init ?? {}
  const opts: RequestInit = {
    credentials: 'same-origin',
    ...rest,
  }
  if (json !== undefined) {
    opts.method = opts.method ?? 'POST'
    opts.headers = { 'Content-Type': 'application/json', ...(opts.headers ?? {}) }
    opts.body = JSON.stringify(json)
  }
  const res = await fetch(path, opts)
  if (res.status === 401 && !authDisabled) {
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    throw new ApiError(401, 'Please sign in')
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (body?.detail) detail = JSON.stringify(body.detail)
    } catch {
      /* not JSON — keep generic message */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

// ---------- Types (field names match the backend exactly) ----------

export interface AuthMe {
  name: string
  auth?: string // "disabled" when auth is off
}

export interface HealthInfo {
  ok: boolean
  keys?: Record<string, boolean>
  auth?: string
  data_as_of?: string
  competitors?: number
  usd_to_inr?: number
  git?: { dirty?: boolean; unpushed?: number | null }
  [k: string]: unknown
}

export interface Competitor {
  pipeline: string
  slug: string
  page_name: string
  total: number
  with_media: number
  by_verdict: {
    strong_winner: number
    winner: number
    undecided: number
    new: number
    loser: number
  }
  generated: number
}

export interface CompetitorsResponse {
  competitors: Competitor[]
  data_as_of?: string
}

export type Verdict = 'strong_winner' | 'winner' | 'undecided' | 'new' | 'loser'

export type TrackerStatus =
  | 'shortlisted'
  | 'generating'
  | 'script_ready'
  | 'in_edit'
  | 'approved'
  | 'in_production'
  | 'shipped'
  | 'dismissed'
  | 'dropped'

export interface JobSummary {
  id: string
  status: JobStatus
  current_step?: string
}

export interface Ad {
  pipeline: string
  competitor: string
  ad_id: string
  page_id: string
  page_name: string
  page_count: number | null
  verdict: Verdict | string
  verdict_confidence: string
  media_type: string
  language: string
  device_format: string
  script_group_id: string
  replication_type: string
  variant_role: string
  first_seen: string
  last_seen: string
  ad_start_date: string
  run_days: number
  run_days_is_lower_bound: boolean
  best_page_rank: number | null
  median_page_rank: number | null
  current_page_rank: number | null
  frac_top_25: number | null
  is_retired: boolean
  present_latest: boolean
  ad_text: string
  cta: string
  destination_url: string
  ad_library_url: string
  media_url: string
  thumb_url: string
  orig_frame_urls: string[]
  gen_panel_urls: string[]
  char_sheet_urls: string[]
  rewrite_gdoc_url: string
  analysis_gdoc_url: string
  rewrite_docx_url: string
  analysis_docx_url: string
  rewrite_html_url: string
  has_docs: boolean
  has_gdocs: boolean
  has_transcript: boolean
  status: TrackerStatus | '' | null
  claimed_by: string
  job: JobSummary | null
}

/** One Library tile in grouped mode: a script + every ad that runs it. */
export interface AdGroup {
  script_group_id: string // '' for an ungrouped (untranscribed) singleton
  representative: Ad // first member matching the current filters, in sort order
  members_matching: number
  group_size_total: number
  languages: string[]
  languages_total: number
  max_run_days: number
  max_run_days_is_lower_bound: boolean
  best_verdict: Verdict | string
  winners: number
  live_count: number
  statuses: Record<string, number>
  member_ids: string[]
}

export interface AdsResponse {
  total: number
  /** grouped mode only: matching ads across all groups / ads with no script group */
  total_ads?: number
  ungrouped_ads?: number
  page: number
  page_size: number
  facets: {
    verdict: Record<string, number>
    media_type: Record<string, number>
    language: Record<string, number>
    device_format: Record<string, number>
    page?: Record<string, number>
  }
  ads: Ad[]
  groups?: AdGroup[]
  data_as_of?: string
}

export interface GroupDetail {
  script_group_id: string
  group_size_total: number
  languages_total: number
  winners_total: number
  members: Ad[]
}

export interface Transcript {
  transcript: string
  summary: string
  on_screen_text: string
  duration_s: number | null
  language: string
}

export interface ActivityEntry {
  ts: string
  who: string
  action: string
  detail: string
}

export interface AdDetail extends Ad {
  transcript: Transcript | null
  rank_timeline: { date: string; rank: number }[]
  related: Ad[]
  group_total: number
  activity: ActivityEntry[]
  latest_job: Job | null
}

export interface Estimate {
  eligible: boolean
  reason?: string
  already_generated?: boolean
  cost_usd?: number
  media_type?: string
  duration_s?: number
  scenes?: number
  notes?: string
  wall_clock?: string
  month_to_date_usd?: number
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'interrupted'
  | 'awaiting_confirm'
  | 'failed'
  | 'cancelled'
  | 'done'

export interface PipelineEstimate {
  eligible: boolean
  reason?: string
  backlog_videos?: number
  backlog_cost_usd?: number
  per_video_usd?: number
  two_phase?: boolean
  note?: string
  excludes?: string
  wall_clock?: string
}

export interface Job {
  id: string
  kind?: 'generate' | 'pipeline'
  pipeline: string
  competitor: string
  ad_id: string
  status: JobStatus
  current_step: string | null
  step_index: number | null
  steps: { key: string; label: string }[]
  requested_by: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  cost_estimate_usd: number | null
  error: string | null
  stderr_tail: string | null
  rewrite_gdoc_url?: string
  analysis_gdoc_url?: string
  rewrite_html_url?: string
  queue_position?: number | null
  /** pipeline runs paused after the free scrape: exact enrichment count + cost */
  enrich?: { videos: number; cost: number; summary: string } | null
}

export interface JobDetail extends Job {
  events: { ts: string; step: string; line: string }[]
}

export interface TrackerRow {
  pipeline: string
  competitor: string
  ad_id: string
  status: TrackerStatus
  claimed_by: string
  requested_by: string
  notes: string
  final_video_url: string
  rewrite_gdoc_url: string
  analysis_gdoc_url: string
  verdict_at_shortlist: string
  created_at: string
  updated_at: string
  script_ready_at: string | null
  ad: {
    page_name: string
    verdict: string
    run_days: number
    media_url: string
    thumb_url: string
    ad_text: string
  } | null
}

// ---------- Endpoint helpers ----------

export const getMe = () => api<AuthMe>('/api/auth/me')
export const login = (password: string, display_name: string) =>
  api<{ name: string }>('/api/auth/login', { json: { password, display_name } })
export const logout = () => api<unknown>('/api/auth/logout', { method: 'POST' })

export const getHealth = () => api<HealthInfo>('/api/health')
export const getCompetitors = () => api<CompetitorsResponse>('/api/competitors')

export const getAds = (params: URLSearchParams) =>
  api<AdsResponse>(`/api/ads?${params.toString()}`)

export const getAd = (pipeline: string, slug: string, adId: string) =>
  api<AdDetail>(
    `/api/ads/${encodeURIComponent(pipeline)}/${encodeURIComponent(slug)}/${encodeURIComponent(adId)}`,
  )

export const getGroup = (pipeline: string, slug: string, gid: string) =>
  api<GroupDetail>(
    `/api/groups/${encodeURIComponent(pipeline)}/${encodeURIComponent(slug)}/${encodeURIComponent(gid)}`,
  )

export const getEstimate = (pipeline: string, slug: string, adId: string) =>
  api<Estimate>(
    `/api/ads/${encodeURIComponent(pipeline)}/${encodeURIComponent(slug)}/${encodeURIComponent(adId)}/estimate`,
  )

export const createJob = (
  pipeline: string,
  competitor: string,
  ad_id: string,
  force = false,
) =>
  api<{ job_id: string }>('/api/jobs', {
    json: { pipeline, competitor, ad_id, force },
  })

export const getJobs = (scope: 'active' | 'recent' | 'all' = 'recent') =>
  api<{ jobs: Job[] }>(`/api/jobs?scope=${scope}`)

export const getJob = (id: string) =>
  api<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`)

export const retryJob = (id: string) =>
  api<unknown>(`/api/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' })

export const cancelJob = (id: string) =>
  api<unknown>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' })

export const getPipelineEstimate = (pipeline: string, competitor: string) =>
  api<PipelineEstimate>(
    `/api/pipeline/estimate?pipeline=${encodeURIComponent(pipeline)}&competitor=${encodeURIComponent(competitor)}`,
  )

export interface PipelinePending {
  per_competitor: Record<string, number>
  total: number
  total_cost_usd: number
  per_video_usd: number
}

export const getPipelinePending = (pipeline: string) =>
  api<PipelinePending>(`/api/pipeline/pending?pipeline=${encodeURIComponent(pipeline)}`)

export const runPipeline = (pipeline: string, competitors: string[]) =>
  api<{ job_ids: number[]; queued: string[]; skipped: string[] }>('/api/pipeline/run', {
    json: { pipeline, competitors },
  })

export const confirmEnrich = (jobId: string, proceed: boolean) =>
  api<{ ok: boolean }>(`/api/jobs/${encodeURIComponent(jobId)}/enrich-confirm`, {
    json: { proceed },
  })

export const getTracker = () => api<{ rows: TrackerRow[] }>('/api/tracker')

export const patchTracker = (
  pipeline: string,
  slug: string,
  adId: string,
  body: {
    status?: string
    claim?: boolean
    notes?: string
    final_video_url?: string
  },
) =>
  api<TrackerRow>(
    `/api/tracker/${encodeURIComponent(pipeline)}/${encodeURIComponent(slug)}/${encodeURIComponent(adId)}`,
    { method: 'PATCH', json: body },
  )

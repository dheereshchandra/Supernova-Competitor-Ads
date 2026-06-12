import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getAd,
  getJob,
  patchTracker,
  type AdDetail as AdDetailT,
  type JobDetail,
} from '../api'
import { useApp } from '../AppContext'
import {
  domainOf,
  friendlyDate,
  friendlyDateTime,
  rankPctLabel,
  runDaysLabel,
  STATUS_FLOW,
} from '../format'
import GenerateModal from '../components/GenerateModal'
import LocalizeModal from '../components/LocalizeModal'
import LocalizedDocsChips from '../components/LocalizedDocsChips'
import {
  ErrorNote,
  PageLoading,
  RankSparkline,
  Spinner,
  StatusChip,
  VerdictBadge,
} from '../components/ui'

const NEXT_LABEL: Record<string, string> = {
  in_edit: 'Mark approved →',
  approved: 'Move to production →',
  in_production: 'Mark shipped →',
}
const NEXT_STATUS: Record<string, string> = {
  in_edit: 'approved',
  approved: 'in_production',
  in_production: 'shipped',
}

export default function AdDetail() {
  const { pipeline = '', slug = '', adId = '' } = useParams()
  const { refreshActiveJobs } = useApp()
  const [ad, setAd] = useState<AdDetailT | null>(null)
  const [error, setError] = useState('')
  const [showGenerate, setShowGenerate] = useState<false | 'normal' | 'force'>(false)
  const [showLocalize, setShowLocalize] = useState(false)
  const [job, setJob] = useState<JobDetail | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getAd(pipeline, slug, adId)
      .then(setAd)
      .catch((e: Error) => setError(e.message))
  }, [pipeline, slug, adId])

  useEffect(() => {
    setAd(null)
    setError('')
    load()
  }, [load])

  // Poll the active job (if any) so progress is live without a refresh.
  const activeJobId =
    ad?.job && (ad.job.status === 'queued' || ad.job.status === 'running')
      ? ad.job.id
      : null
  useEffect(() => {
    if (!activeJobId) {
      setJob(null)
      return
    }
    let stop = false
    const tick = () => {
      getJob(activeJobId)
        .then((j) => {
          if (stop) return
          setJob(j)
          if (j.status === 'done' || j.status === 'failed') {
            load()
            refreshActiveJobs()
          }
        })
        .catch(() => {})
    }
    tick()
    const t = window.setInterval(tick, 3000)
    return () => {
      stop = true
      window.clearInterval(t)
    }
  }, [activeJobId, load, refreshActiveJobs])

  const setStatus = async (status: string, extra?: { claim?: boolean }) => {
    setBusy(true)
    try {
      await patchTracker(pipeline, slug, adId, { status, ...extra })
      load()
      refreshActiveJobs()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (error) return <ErrorNote message={error} />
  if (!ad) return <PageLoading label="Loading ad…" />

  const isVideo = (ad.media_type || '').toLowerCase().includes('video')
  const status = ad.status || ''
  const hasDocs = ad.has_gdocs || ad.has_docs
  const scriptLink = ad.rewrite_gdoc_url || ad.rewrite_html_url || ad.rewrite_docx_url
  const analysisLink = ad.analysis_gdoc_url || ad.analysis_docx_url

  return (
    <div className="fade-in-up">
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300">
        ← Back to library
      </Link>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_1fr]">
        {/* LEFT: media + copy */}
        <div className="space-y-4">
          <div className="overflow-hidden rounded-2xl border border-white/10 bg-black">
            {ad.media_url ? (
              isVideo ? (
                <video
                  controls
                  autoPlay
                  muted
                  loop
                  playsInline
                  poster={ad.thumb_url || undefined}
                  src={ad.media_url}
                  className="max-h-[70vh] w-full bg-black object-contain"
                />
              ) : (
                <img src={ad.media_url} alt="" className="max-h-[70vh] w-full object-contain" />
              )
            ) : (
              <div className="flex aspect-video items-center justify-center text-zinc-600">
                No media available
              </div>
            )}
          </div>

          {ad.ad_text && (
            <div className="rounded-xl border border-white/10 bg-zinc-900/60 p-4">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">
                Ad copy
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
                {ad.ad_text}
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {ad.cta && (
              <span className="rounded-full border border-violet-400/30 bg-violet-500/15 px-3 py-1 text-xs font-medium text-violet-200">
                {ad.cta}
              </span>
            )}
            {ad.ad_library_url && (
              <a
                href={ad.ad_library_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-300 hover:bg-white/5"
              >
                View in Ad Library ↗
              </a>
            )}
            {ad.destination_url && (
              <a
                href={ad.destination_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-white/10 px-3 py-1 text-xs text-zinc-300 hover:bg-white/5"
              >
                {domainOf(ad.destination_url) || 'Landing page'} ↗
              </a>
            )}
          </div>

          {/* Transcript */}
          {ad.transcript ? (
            <details className="rounded-xl border border-white/10 bg-zinc-900/60 p-4" open>
              <summary className="cursor-pointer text-sm font-medium text-zinc-200">
                What's said in the ad
              </summary>
              <div className="mt-3 space-y-3 text-sm">
                {ad.transcript.summary && (
                  <p className="font-medium text-zinc-200">{ad.transcript.summary}</p>
                )}
                {ad.transcript.transcript && (
                  <p className="whitespace-pre-wrap leading-relaxed text-zinc-400">
                    {ad.transcript.transcript}
                  </p>
                )}
                {ad.transcript.on_screen_text && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                      On-screen text
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-zinc-400">
                      {ad.transcript.on_screen_text}
                    </p>
                  </div>
                )}
              </div>
            </details>
          ) : (
            <p className="text-xs text-zinc-600">No transcript for this ad yet.</p>
          )}

          {/* Related */}
          {ad.related.length > 0 && (
            <div>
              <div className="mb-2 flex items-baseline justify-between gap-2 text-sm text-zinc-400">
                <span>
                  This competitor ran {ad.group_total || ad.related.length + 1} variants
                  of this script
                </span>
                {ad.group_total > ad.related.length + 1 && (
                  <Link
                    to={`/?${new URLSearchParams({
                      ...(ad.pipeline !== 'facebook' ? { pipeline: ad.pipeline } : {}),
                      competitor: ad.competitor,
                      g: `${ad.competitor}::${ad.script_group_id}`,
                    }).toString()}`}
                    className="shrink-0 text-xs text-violet-400 hover:underline"
                  >
                    View all {ad.group_total} →
                  </Link>
                )}
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {ad.related.map((r) => (
                  <Link
                    key={r.ad_id}
                    to={`/ad/${r.pipeline}/${r.competitor}/${r.ad_id}`}
                    className="w-20 shrink-0"
                  >
                    <div className="h-28 overflow-hidden rounded-lg border border-white/10 bg-zinc-900">
                      {r.media_url && (r.media_type || '').toLowerCase().includes('video') ? (
                        <video src={r.media_url} muted className="h-full w-full object-cover" />
                      ) : r.media_url ? (
                        <img src={r.media_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-lg opacity-30">🎬</div>
                      )}
                    </div>
                    <div className="mt-0.5 truncate text-center text-[10px] text-zinc-500">
                      {r.language || '—'}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: action + why-it-wins */}
        <div className="space-y-4">
          {/* ACTION BLOCK */}
          <div className="rounded-2xl border border-white/10 bg-zinc-900/80 p-5">
            <div className="mb-3 flex items-center gap-2">
              <VerdictBadge verdict={ad.verdict} />
              {status && <StatusChip status={status} suffix={ad.claimed_by || undefined} />}
            </div>

            {/* live job */}
            {job && (job.status === 'queued' || job.status === 'running') ? (
              <JobProgressInline job={job} />
            ) : !status ? (
              <div className="space-y-2">
                <button
                  onClick={() => setStatus('shortlisted')}
                  disabled={busy}
                  className="w-full rounded-lg bg-amber-500/90 px-4 py-2.5 text-sm font-semibold text-amber-950 hover:bg-amber-400 disabled:opacity-60"
                >
                  ⭐ Shortlist this ad
                </button>
                {hasDocs && (
                  <DocButtons script={scriptLink} analysis={analysisLink} />
                )}
                <button
                  onClick={() => setStatus('dismissed')}
                  disabled={busy}
                  className="w-full rounded-lg px-4 py-2 text-xs text-zinc-500 hover:bg-white/5"
                >
                  Not for us — dismiss
                </button>
              </div>
            ) : status === 'shortlisted' ? (
              <div className="space-y-2">
                {hasDocs ? (
                  <>
                    <div className="rounded-lg border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                      Script docs already exist for this ad.
                    </div>
                    <DocButtons script={scriptLink} analysis={analysisLink} />
                    <button
                      onClick={() => setShowGenerate('force')}
                      className="w-full rounded-lg border border-white/10 px-4 py-2 text-xs text-zinc-400 hover:bg-white/5"
                    >
                      Re-generate (paid)
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setShowGenerate('normal')}
                    className="w-full rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 hover:bg-violet-500"
                  >
                    ✨ Generate Supernova Script…
                  </button>
                )}
                <button
                  onClick={() => setStatus('dismissed')}
                  disabled={busy}
                  className="w-full rounded-lg px-4 py-2 text-xs text-zinc-500 hover:bg-white/5"
                >
                  Dismiss
                </button>
              </div>
            ) : status === 'dismissed' || status === 'dropped' ? (
              <div className="space-y-2">
                <div className="rounded-lg border border-white/10 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-400">
                  This ad was {status}.
                </div>
                <button
                  onClick={() => setStatus('shortlisted')}
                  disabled={busy}
                  className="w-full rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5"
                >
                  Restore to shortlist
                </button>
              </div>
            ) : (
              /* script_ready and beyond */
              <div className="space-y-3">
                <DocButtons script={scriptLink} analysis={analysisLink} />
                {scriptLink && (
                  <button
                    onClick={() => setShowLocalize(true)}
                    disabled={busy}
                    className="w-full rounded-lg border border-violet-400/30 bg-violet-600/15 px-4 py-2 text-sm font-medium text-violet-200 hover:bg-violet-600/25 disabled:opacity-60"
                  >
                    🌍 Replicate to languages
                  </button>
                )}
                <LocalizedDocsChips
                  pipeline={pipeline}
                  competitor={slug}
                  adId={adId}
                  locales={ad.locales || {}}
                  verified={ad.verified_languages || {}}
                  onChanged={load}
                />
                <StatusStepper status={status} />
                {status === 'script_ready' &&
                  (ad.claimed_by ? (
                    <div className="text-xs text-zinc-500">Claimed by {ad.claimed_by}</div>
                  ) : (
                    <button
                      onClick={() => setStatus('in_edit', { claim: true })}
                      disabled={busy}
                      className="w-full rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-60"
                    >
                      📝 Claim & start editing
                    </button>
                  ))}
                {NEXT_STATUS[status] && (
                  <button
                    onClick={() => setStatus(NEXT_STATUS[status])}
                    disabled={busy}
                    className="w-full rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-white/5 disabled:opacity-60"
                  >
                    {NEXT_LABEL[status]}
                  </button>
                )}
                {(status === 'approved' || status === 'in_production' || status === 'shipped') && (
                  <FinalVideoField
                    pipeline={pipeline}
                    slug={slug}
                    adId={adId}
                    initial={''}
                    onSaved={load}
                  />
                )}
                <button
                  onClick={() => setStatus('dropped')}
                  disabled={busy}
                  className="w-full rounded-lg px-4 py-1.5 text-xs text-zinc-600 hover:bg-white/5"
                >
                  Drop from pipeline
                </button>
              </div>
            )}
          </div>

          {/* WHY IT'S A WINNER */}
          <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-5">
            <div className="mb-3 text-sm font-medium text-zinc-300">Why it's a winner</div>
            <div className="mb-4 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-white">🔥 {runDaysLabel(ad)}</span>
              {!ad.is_retired ? (
                <span className="text-xs font-medium text-emerald-400">still live</span>
              ) : (
                <span className="text-xs text-zinc-500">no longer running</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat
                label="Best rank"
                value={
                  ad.best_page_rank != null
                    ? `#${ad.best_page_rank}${ad.page_count ? ` / ${ad.page_count}` : ''}`
                    : '—'
                }
                sub={
                  ad.page_count != null && ad.page_count >= 20
                    ? rankPctLabel(ad.best_page_rank, ad.page_count)
                    : undefined
                }
              />
              <Stat
                label="Current"
                value={
                  ad.current_page_rank != null
                    ? `#${ad.current_page_rank}${ad.page_count ? ` / ${ad.page_count}` : ''}`
                    : '—'
                }
                sub={
                  ad.page_count != null && ad.page_count >= 20
                    ? rankPctLabel(ad.current_page_rank, ad.page_count)
                    : undefined
                }
              />
              <Stat
                label="In top 25%"
                value={ad.frac_top_25 != null ? `${Math.round(ad.frac_top_25 * 100)}%` : '—'}
              />
            </div>
            <div className="mt-4">
              <div className="mb-1 text-xs text-zinc-500">Rank over time</div>
              <RankSparkline points={ad.rank_timeline} />
            </div>
            <dl className="mt-4 space-y-1.5 text-xs">
              <Row k="First seen" v={friendlyDate(ad.first_seen)} />
              <Row k="Last seen" v={friendlyDate(ad.last_seen)} />
              {ad.language && <Row k="Language" v={ad.language} />}
              {ad.device_format && <Row k="Format" v={ad.device_format} />}
              <Row k="Confidence" v={ad.verdict_confidence || '—'} />
            </dl>
          </div>

          {/* Activity */}
          {ad.activity.length > 0 && (
            <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-5">
              <div className="mb-2 text-sm font-medium text-zinc-300">Activity</div>
              <ul className="space-y-1.5 text-xs text-zinc-500">
                {ad.activity.map((a, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span>
                      <span className="text-zinc-300">{a.who}</span> {a.action}
                      {a.detail ? ` — ${a.detail}` : ''}
                    </span>
                    <span className="shrink-0 text-zinc-600">{friendlyDateTime(a.ts)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {showGenerate && (
        <GenerateModal
          pipeline={pipeline}
          competitor={slug}
          adId={adId}
          force={showGenerate === 'force'}
          onClose={() => setShowGenerate(false)}
          onStarted={() => {
            setShowGenerate(false)
            load()
            refreshActiveJobs()
          }}
        />
      )}
      {showLocalize && (
        <LocalizeModal
          pipeline={pipeline}
          competitor={slug}
          adId={adId}
          suggestedLanguages={[
            ...new Set(
              [ad.language, ...ad.related.map((r) => r.language)].filter(Boolean),
            ),
          ]}
          alreadyLocalized={Object.keys(ad.locales || {})}
          onClose={() => setShowLocalize(false)}
          onStarted={() => {
            setShowLocalize(false)
            load()
            refreshActiveJobs()
          }}
        />
      )}
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-2 py-2">
      <div className="text-base font-semibold text-zinc-100">{value}</div>
      {sub && <div className="text-[10px] font-medium text-violet-300">{sub}</div>}
      <div className="text-[11px] text-zinc-500">{label}</div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-zinc-500">{k}</dt>
      <dd className="text-zinc-300">{v}</dd>
    </div>
  )
}

function DocButtons({ script, analysis }: { script: string; analysis: string }) {
  return (
    <div className="grid grid-cols-1 gap-2">
      {script && (
        <a
          href={script}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg bg-emerald-600 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-emerald-500"
        >
          📝 Open Supernova Script
        </a>
      )}
      {analysis && (
        <a
          href={analysis}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-white/15 px-4 py-2.5 text-center text-sm font-medium text-zinc-200 hover:bg-white/5"
        >
          🔍 Open Competitor Analysis
        </a>
      )}
    </div>
  )
}

function StatusStepper({ status }: { status: string }) {
  const idx = STATUS_FLOW.indexOf(status as (typeof STATUS_FLOW)[number])
  return (
    <div className="flex items-center gap-1">
      {STATUS_FLOW.filter((s) => s !== 'generating').map((s) => {
        const si = STATUS_FLOW.indexOf(s)
        const done = si <= idx
        return (
          <div
            key={s}
            title={s.replace('_', ' ')}
            className={`h-1.5 flex-1 rounded-full ${done ? 'bg-violet-500' : 'bg-white/10'}`}
          />
        )
      })}
    </div>
  )
}

function JobProgressInline({ job }: { job: JobDetail }) {
  const idx = job.step_index ?? -1
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium text-violet-300">
        <Spinner className="h-4 w-4" /> Generating your script…
      </div>
      <div className="space-y-1">
        {job.steps.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2 text-xs">
            <span className="w-4 text-center">
              {i < idx ? '✓' : i === idx ? '⟳' : '·'}
            </span>
            <span className={i === idx ? 'text-zinc-200' : i < idx ? 'text-zinc-500' : 'text-zinc-600'}>
              {s.label}
            </span>
          </div>
        ))}
      </div>
      <Link to="/runs" className="inline-block text-xs text-violet-400 hover:underline">
        View in Runs →
      </Link>
    </div>
  )
}

function FinalVideoField({
  pipeline,
  slug,
  adId,
  initial,
  onSaved,
}: {
  pipeline: string
  slug: string
  adId: string
  initial: string
  onSaved: () => void
}) {
  const [url, setUrl] = useState(initial)
  const [saved, setSaved] = useState(false)
  const t = useRef<number | null>(null)
  const save = (v: string) => {
    if (t.current) window.clearTimeout(t.current)
    t.current = window.setTimeout(() => {
      patchTracker(pipeline, slug, adId, { final_video_url: v })
        .then(() => {
          setSaved(true)
          onSaved()
          window.setTimeout(() => setSaved(false), 1500)
        })
        .catch(() => {})
    }, 700)
  }
  return (
    <div>
      <label className="mb-1 block text-xs text-zinc-500">
        Final Supernova video link {saved && <span className="text-emerald-400">saved ✓</span>}
      </label>
      <input
        value={url}
        onChange={(e) => {
          setUrl(e.target.value)
          save(e.target.value)
        }}
        placeholder="Paste the produced video URL"
        className="w-full rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-xs text-white outline-none focus:border-violet-400/50"
      />
    </div>
  )
}

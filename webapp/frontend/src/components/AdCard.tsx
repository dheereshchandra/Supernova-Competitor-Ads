import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Ad } from '../api'
import { runDaysLabel } from '../format'
import { StatusChip, VerdictBadge, Spinner } from './ui'

/**
 * Library card. The <video> element is only mounted while the card is near the
 * viewport (IntersectionObserver) so a 60-card grid stays light. Hovering
 * plays the video muted; leaving pauses and rewinds it.
 */
// Server-extracted poster (tiny JPG, cached). Far lighter than streaming the MP4
// just to show a still — and it avoids a grid of <video> tags hammering R2.
function posterUrl(ad: Ad): string {
  if (ad.thumb_url) return ad.thumb_url
  return `/api/thumb/${ad.pipeline}/${ad.competitor}/${ad.ad_id}`
}

export default function AdCard({ ad }: { ad: Ad }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [inView, setInView] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [mediaBroken, setMediaBroken] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) setInView(e.isIntersecting)
      },
      { rootMargin: '200px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // facebook uses "Video", google uses "YouTubeVideo"
  const isVideo =
    !!ad.media_url && (ad.media_type || '').toLowerCase().includes('video')
  const isImage = !isVideo && !!ad.media_url

  // Mount the <video> ONLY while hovering (and in view) so a full grid never
  // opens dozens of MP4 connections at once — the poster carries the at-a-glance view.
  const showVideo = inView && hovered && isVideo && !mediaBroken
  const onEnter = () => setHovered(true)
  const onLeave = () => {
    setHovered(false)
    const v = videoRef.current
    if (v) {
      v.pause()
      v.currentTime = 0
    }
  }

  const jobActive =
    ad.job && (ad.job.status === 'queued' || ad.job.status === 'running')

  return (
    <Link
      to={`/ad/${ad.pipeline}/${ad.competitor}/${ad.ad_id}`}
      className="group block"
    >
      <div
        ref={ref}
        className="overflow-hidden rounded-xl border border-white/10 bg-zinc-900/60 transition-all duration-200 hover:-translate-y-0.5 hover:border-violet-400/40 hover:shadow-xl hover:shadow-violet-950/40"
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
      >
        {/* Media area (fixed aspect → every tile is the same size) */}
        <div className="relative aspect-[9/13] w-full overflow-hidden bg-zinc-900">
          {showVideo ? (
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              loop
              poster={posterUrl(ad)}
              src={ad.media_url}
              className="h-full w-full object-cover"
              onError={() => setMediaBroken(true)}
            />
          ) : inView && (isVideo || isImage) && !mediaBroken ? (
            <img
              src={isImage ? ad.media_url : posterUrl(ad)}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
              onError={() => setMediaBroken(true)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-zinc-900 to-zinc-800">
              <span className="text-3xl opacity-30">
                {ad.media_type === 'Video' ? '🎬' : '🖼️'}
              </span>
            </div>
          )}
          {/* play affordance on the poster */}
          {!showVideo && (isVideo || isImage) && !mediaBroken && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur-sm">▶</span>
            </div>
          )}

          {/* top-left verdict badge */}
          <div className="absolute left-2 top-2">
            <VerdictBadge verdict={ad.verdict} />
          </div>
          {/* media-type tag for non-video */}
          {ad.media_type && !isVideo && (
            <div className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
              {ad.media_type}
            </div>
          )}
        </div>

        {/* compact, FIXED-height footer so every tile is identical */}
        <div className="space-y-1 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1 text-xs font-semibold text-zinc-100">
              🔥 {runDaysLabel(ad)}
            </span>
            {!ad.is_retired ? (
              <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                live
              </span>
            ) : (
              <span className="text-[10px] text-zinc-500">retired</span>
            )}
          </div>
          <div className="truncate text-[11px] text-zinc-400">{ad.page_name}</div>
          {/* reserved status row (keeps tiles uniform whether or not a chip shows) */}
          <div className="flex h-[18px] items-center">
            {jobActive ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-300">
                <Spinner className="h-2.5 w-2.5" />
                Generating…
              </span>
            ) : ad.status ? (
              <StatusChip
                status={ad.status}
                suffix={ad.status === 'in_edit' && ad.claimed_by ? ad.claimed_by : undefined}
              />
            ) : null}
          </div>
        </div>
      </div>
    </Link>
  )
}

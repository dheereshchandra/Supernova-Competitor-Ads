import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { getJobs, getMe, getHealth, setAuthDisabled, type Job } from './api'
import { setUsdToInr } from './format'

interface AppState {
  /** null = still checking; '' = not signed in */
  userName: string | null
  authDisabled: boolean
  authChecked: boolean
  setUserName: (n: string) => void
  dataAsOf: string | null
  noteDataAsOf: (s: string | null | undefined) => void
  /** Jobs currently queued/running, polled app-wide every 10s. */
  activeJobs: Job[]
  /** True once the jobs API has answered at least once (404 counts as answered). */
  jobsApiAvailable: boolean
  refreshActiveJobs: () => void
  /** Bumps whenever a data-pipeline run finishes — screens watch it to re-fetch. */
  dataVersion: number
  /** True when the backend (the operator's Mac) can't be reached — drives the offline overlay. */
  serverDown: boolean
}

const Ctx = createContext<AppState | null>(null)

/** Lightweight reachability ping — /api/health is unauthenticated, so 200 = up. */
async function pingHealth(): Promise<boolean> {
  try {
    const ctrl = new AbortController()
    const t = window.setTimeout(() => ctrl.abort(), 8000)
    const r = await fetch('/api/health', { cache: 'no-store', signal: ctrl.signal })
    window.clearTimeout(t)
    return r.ok
  } catch {
    return false // network error / timeout / tunnel reports the origin is down
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [userName, setUserName] = useState<string | null>(null)
  const [authDis, setAuthDis] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [dataAsOf, setDataAsOf] = useState<string | null>(null)
  const [activeJobs, setActiveJobs] = useState<Job[]>([])
  const [jobsApiAvailable, setJobsApiAvailable] = useState(true)
  const [dataVersion, setDataVersion] = useState(0)
  const [serverDown, setServerDown] = useState(false)
  const prevPipelineJobs = useRef<Map<string, string>>(new Map())
  const failRef = useRef(0)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((me) => {
        if (cancelled) return
        if (me.auth === 'disabled') {
          setAuthDisabled(true)
          setAuthDis(true)
        }
        setUserName(me.name ?? '')
        setAuthChecked(true)
      })
      .catch(() => {
        if (cancelled) return
        setUserName('')
        setAuthChecked(true)
      })
    getHealth()
      .then((h) => {
        if (cancelled) return
        if (h.data_as_of) setDataAsOf(h.data_as_of)
        setUsdToInr(h.usd_to_inr)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const refreshActiveJobs = useCallback(() => {
    getJobs('active')
      .then((r) => {
        const jobs = r.jobs ?? []
        // New data lands twice in a pipeline run: when the free scrape commits
        // (job → awaiting_confirm) and when it fully finishes (job disappears).
        // Bump dataVersion on either so every screen re-fetches.
        const nowMap = new Map(
          jobs.filter((j) => j.kind === 'pipeline').map((j) => [String(j.id), j.status]),
        )
        let changed = false
        prevPipelineJobs.current.forEach((_st, id) => {
          if (!nowMap.has(id)) changed = true // finished/skipped → gone from active
        })
        nowMap.forEach((st, id) => {
          if (st === 'awaiting_confirm' && prevPipelineJobs.current.get(id) !== 'awaiting_confirm')
            changed = true // free phase just committed
        })
        prevPipelineJobs.current = nowMap
        if (changed) setDataVersion((v) => v + 1)
        setActiveJobs(jobs)
        setJobsApiAvailable(true)
      })
      .catch((e: unknown) => {
        setActiveJobs([])
        // 404 = the generation service isn't deployed yet; stay quiet.
        if ((e as { status?: number })?.status === 404) setJobsApiAvailable(false)
      })
  }, [])

  useEffect(() => {
    refreshActiveJobs()
    pollRef.current = window.setInterval(refreshActiveJobs, 10_000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [refreshActiveJobs])

  // Reachability watcher — show the offline overlay after 2 consecutive misses
  // (so a single network blip doesn't flash it).
  useEffect(() => {
    let cancelled = false
    const check = async () => {
      const up = await pingHealth()
      if (cancelled) return
      if (up) {
        failRef.current = 0
        setServerDown(false)
      } else {
        failRef.current += 1
        if (failRef.current >= 2) setServerDown(true)
      }
    }
    check()
    const id = window.setInterval(check, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  const noteDataAsOf = useCallback((s: string | null | undefined) => {
    if (s) setDataAsOf(s)
  }, [])

  return (
    <Ctx.Provider
      value={{
        userName,
        authDisabled: authDis,
        authChecked,
        setUserName,
        dataAsOf,
        noteDataAsOf,
        activeJobs,
        jobsApiAvailable,
        refreshActiveJobs,
        dataVersion,
        serverDown,
      }}
    >
      {children}
    </Ctx.Provider>
  )
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp outside AppProvider')
  return v
}

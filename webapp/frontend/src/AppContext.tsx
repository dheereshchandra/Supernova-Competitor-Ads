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
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [userName, setUserName] = useState<string | null>(null)
  const [authDis, setAuthDis] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [dataAsOf, setDataAsOf] = useState<string | null>(null)
  const [activeJobs, setActiveJobs] = useState<Job[]>([])
  const [jobsApiAvailable, setJobsApiAvailable] = useState(true)
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
        if (!cancelled && h.data_as_of) setDataAsOf(h.data_as_of)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const refreshActiveJobs = useCallback(() => {
    getJobs('active')
      .then((r) => {
        setActiveJobs(r.jobs ?? [])
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

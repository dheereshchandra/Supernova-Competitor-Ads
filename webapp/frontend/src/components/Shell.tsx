import { NavLink, Outlet } from 'react-router-dom'
import { useApp } from '../AppContext'
import { friendlyDateTime } from '../format'

const NAV = [
  { to: '/', label: 'Library' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/runs', label: 'Runs' },
  { to: '/health', label: 'Health' },
]

export default function Shell() {
  const { userName, dataAsOf, activeJobs } = useApp()
  const generating = activeJobs.length

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-zinc-950/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-6 px-6">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-600 text-sm shadow-lg shadow-violet-900/40">
              ✨
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-white">
              Supernova Ad Studio
            </span>
          </NavLink>

          <nav className="flex items-center gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `relative rounded-lg px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-white/10 font-medium text-white'
                      : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                  }`
                }
              >
                {n.label}
                {n.to === '/runs' && generating > 0 && (
                  <span className="ml-1.5 inline-flex items-center gap-1 rounded-full bg-violet-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
                    {generating}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            {generating > 0 && (
              <NavLink
                to="/runs"
                className="hidden items-center gap-1.5 rounded-full border border-violet-400/30 bg-violet-500/15 px-3 py-1 text-xs font-medium text-violet-300 lg:flex"
              >
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
                {generating} generating
              </NavLink>
            )}
            {dataAsOf && (
              <span className="hidden text-xs text-zinc-500 xl:block">
                Data as of {friendlyDateTime(dataAsOf)}
              </span>
            )}
            {userName ? (
              <span className="flex items-center gap-2 text-sm text-zinc-300">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-violet-500/25 text-[11px] font-semibold uppercase text-violet-200">
                  {userName.slice(0, 1)}
                </span>
                {userName}
              </span>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}

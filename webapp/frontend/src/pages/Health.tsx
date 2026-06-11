import { useEffect, useState } from 'react'
import { getHealth, logout, type HealthInfo } from '../api'
import { friendlyDateTime } from '../format'
import { ErrorNote, PageLoading } from '../components/ui'

const SHEET_URL =
  'https://docs.google.com/spreadsheets/d/1Iy6gKifge9Y2B1kwXZL2nd3r2xCudB0HB9UNYzyxxRI/edit'

const KEY_LABELS: Record<string, string> = {
  R2_S3_ENDPOINT: 'R2 storage',
  R2_ACCESS_KEY_ID: 'R2 access key',
  R2_SECRET_ACCESS_KEY: 'R2 secret',
  R2_BUCKET: 'R2 bucket',
  R2_PUBLIC_URL_BASE: 'R2 public URL',
  GEMINI_API_KEY: 'Gemini AI',
  GOOGLE_SERVICE_ACCOUNT_JSON: 'Google service account',
  GDRIVE_SHARED_DRIVE_ID: 'Shared Drive',
  STUDIO_PASSWORD: 'Team password',
  STUDIO_SESSION_SECRET: 'Session secret',
}

export default function Health() {
  const [h, setH] = useState<HealthInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getHealth()
      .then(setH)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <ErrorNote message={error} />
  if (!h) return <PageLoading label="Checking system…" />

  const git = h.git ?? {}

  return (
    <div className="fade-in-up max-w-2xl space-y-5">
      <h1 className="text-lg font-semibold text-white">System health</h1>

      <div className="grid grid-cols-2 gap-3">
        <Tile label="Competitors tracked" value={String(h.competitors ?? '—')} />
        <Tile label="Data refreshed" value={friendlyDateTime(h.data_as_of)} />
        <Tile
          label="Repository"
          value={git.dirty ? 'Has uncommitted changes' : 'Clean'}
          good={!git.dirty}
        />
        <Tile
          label="Sign-in"
          value={h.auth?.includes('DISABLED') ? 'Open (dev)' : 'Password on'}
          good={!h.auth?.includes('DISABLED')}
        />
      </div>

      <div className="rounded-xl border border-white/10 bg-zinc-900/60 p-5">
        <div className="mb-3 text-sm font-medium text-zinc-300">Connections</div>
        <div className="grid grid-cols-2 gap-y-2 gap-x-6">
          {Object.entries(h.keys ?? {}).map(([k, ok]) => (
            <div key={k} className="flex items-center gap-2 text-sm">
              <span className={`h-2 w-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span className="text-zinc-400">{KEY_LABELS[k] ?? k}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-zinc-900/60 p-5">
        <div className="mb-2 text-sm font-medium text-zinc-300">Links</div>
        <a
          href={SHEET_URL}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-violet-400 hover:underline"
        >
          Supernova Competitor Master sheet ↗
        </a>
      </div>

      {!h.auth?.includes('DISABLED') && (
        <button
          onClick={() => logout().then(() => (window.location.href = '/login'))}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-400 hover:bg-white/5"
        >
          Sign out
        </button>
      )}
    </div>
  )
}

function Tile({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/60 p-4">
      <div className="text-xs text-zinc-500">{label}</div>
      <div
        className={`mt-1 text-sm font-medium ${
          good === undefined ? 'text-zinc-200' : good ? 'text-emerald-300' : 'text-amber-300'
        }`}
      >
        {value}
      </div>
    </div>
  )
}

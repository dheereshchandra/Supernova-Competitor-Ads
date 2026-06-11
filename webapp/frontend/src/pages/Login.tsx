import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api'
import { useApp } from '../AppContext'
import { Spinner } from '../components/ui'

export default function Login() {
  const { authChecked, authDisabled, userName, setUserName } = useApp()
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Auth off (local dev) or already signed in → skip the gate.
  useEffect(() => {
    if (authChecked && (authDisabled || userName)) nav('/', { replace: true })
  }, [authChecked, authDisabled, userName, nav])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await login(password, name)
      setUserName(r.name)
      nav('/', { replace: true })
    } catch (err) {
      setError((err as Error).message || 'Could not sign in')
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="fade-in-up w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-600 text-xl shadow-lg shadow-violet-900/40">
            ✨
          </span>
          <div>
            <h1 className="text-xl font-semibold text-white">Supernova Ad Studio</h1>
            <p className="mt-1 text-sm text-zinc-500">
              Find winning competitor ads and turn them into Supernova scripts.
            </p>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="space-y-4 rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-xl"
        >
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">
              Your name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Maya"
              autoFocus
              className="w-full rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-violet-400/50"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">
              Team password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-zinc-950/60 px-3 py-2 text-sm text-white outline-none focus:border-violet-400/50"
            />
          </div>
          {error && (
            <div className="rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy || !name || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-950/50 transition-colors hover:bg-violet-500 disabled:opacity-50"
          >
            {busy && <Spinner className="h-4 w-4 text-white" />}
            Enter the studio
          </button>
        </form>
      </div>
    </div>
  )
}

import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppProvider, useApp } from './AppContext'
import Shell from './components/Shell'
import { PageLoading } from './components/ui'
import Library from './pages/Library'
import AdDetail from './pages/AdDetail'
import Pipeline from './pages/Pipeline'
import Runs from './pages/Runs'
import Health from './pages/Health'
import Login from './pages/Login'

/** Blocks the app until we know who you are; bounces to /login when signed out. */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { authChecked, userName, authDisabled } = useApp()
  const loc = useLocation()
  if (!authChecked) return <PageLoading label="Starting the studio…" />
  if (!userName && !authDisabled) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <AuthGate>
                <Shell />
              </AuthGate>
            }
          >
            <Route path="/" element={<Library />} />
            <Route path="/ad/:pipeline/:slug/:adId" element={<AdDetail />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/health" element={<Health />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppProvider>
    </BrowserRouter>
  )
}

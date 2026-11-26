import { StrictMode, lazy, Suspense, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import { AppProvider, useApp } from './lib/app-context'
import Login from './pages/Login'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Assistant = lazy(() => import('./pages/Assistant'))
const Knowledge = lazy(() => import('./pages/Knowledge'))
const Disease = lazy(() => import('./pages/Disease'))
const Soil = lazy(() => import('./pages/Soil'))
const Farming = lazy(() => import('./pages/Farming'))
const Schemes = lazy(() => import('./pages/Schemes'))
const Weather = lazy(() => import('./pages/Weather'))
const Lab = lazy(() => import('./pages/Lab'))
const Evaluation = lazy(() => import('./pages/Evaluation'))
const Admin = lazy(() => import('./pages/Admin'))

function Guard({ children, admin }: { children: ReactNode; admin?: boolean }) {
  const { user, ready } = useApp()
  if (!ready) return <div className="p-10"><Spinner /></div>
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return <>{children}</>
}

function App() {
  const { user, ready } = useApp()
  return (
    <Suspense fallback={<div className="p-10"><Spinner /></div>}>
      <Routes>
        <Route path="/login" element={ready && user ? <Navigate to="/" replace /> : <Login />} />
        <Route element={<Guard><Layout /></Guard>}>
          <Route index element={<Dashboard />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="assistant/:id" element={<Assistant />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="disease" element={<Disease />} />
          <Route path="soil" element={<Soil />} />
          <Route path="farming" element={<Farming />} />
          <Route path="schemes" element={<Schemes />} />
          <Route path="weather" element={<Weather />} />
          <Route path="lab" element={<Lab />} />
          <Route path="evaluation" element={<Evaluation />} />
          <Route path="admin" element={<Guard admin><Admin /></Guard>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><BrowserRouter><AppProvider><App /></AppProvider></BrowserRouter></StrictMode>,
)

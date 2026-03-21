import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { getToken } from './services/api_client'
import LoginPage from './pages/login'
import DashboardPage from './pages/dashboard'
import IncidentDetailPage from './pages/incidents'
import RunbookChatPage from './pages/runbook_chat'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
        <Route path="/incidents/:id" element={<ProtectedRoute><IncidentDetailPage /></ProtectedRoute>} />
        <Route path="/runbooks" element={<ProtectedRoute><RunbookChatPage /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}

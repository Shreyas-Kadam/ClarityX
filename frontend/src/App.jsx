import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { PublicOnlyRoute } from './components/auth/PublicOnlyRoute'
import { AppLayout } from './components/layout/AppLayout'

import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { DashboardPage } from './pages/DashboardPage'
import { NewResearchPage } from './pages/NewResearchPage'
import { ResearchHistoryPage } from './pages/ResearchHistoryPage'
import { ResearchDetailPage } from './pages/ResearchDetailPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public-only authentication routes */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {/* Authenticated protected application routes */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/new" element={<NewResearchPage />} />
            <Route path="/history" element={<ResearchHistoryPage />} />
            <Route path="/research/:id" element={<ResearchDetailPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>

        {/* Catch-all route redirects to root (which triggers ProtectedRoute check) */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}

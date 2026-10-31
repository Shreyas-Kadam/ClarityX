import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { DashboardPage } from './pages/DashboardPage'
import { NewResearchPage } from './pages/NewResearchPage'
import { ResearchHistoryPage } from './pages/ResearchHistoryPage'
import { ResearchDetailPage } from './pages/ResearchDetailPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/new" element={<NewResearchPage />} />
        <Route path="/history" element={<ResearchHistoryPage />} />
        <Route path="/research/:id" element={<ResearchDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      {/* Catch-all redirect to Dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

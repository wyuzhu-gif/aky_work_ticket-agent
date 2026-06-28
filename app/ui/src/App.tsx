import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import TicketReview from './pages/ticketReview/TicketReview'
import SmartQuery from './pages/smartQuery/SmartQuery'
import AgentAdmin from './pages/agentAdmin/AgentAdmin'
import HermesChat from './pages/hermesChat/HermesChat'
import type { ThemeMode } from './theme'

type AppProps = {
  mode: ThemeMode
  onToggleMode: () => void
}

function App({ mode, onToggleMode }: AppProps) {
  return (
    <AppShell mode={mode} onToggleMode={onToggleMode}>
      <Pages />
    </AppShell>
  )
}

function Pages() {
  return (
    <Routes>
      {/* 默认跳到作业票审查 (2026-06-12 简化为 3 大功能) */}
      <Route path="/" element={<Navigate to="/ticket-review" replace />} />

      {/* 作业票管理 */}
      <Route path="/ticket-review" element={<TicketReview />} />

      {/* 数据分析 */}
      <Route path="/smart-query" element={<SmartQuery />} />
      <Route path="/hermes-chat" element={<HermesChat />} />

      {/* 系统管理 */}
      <Route path="/agent-admin" element={<AgentAdmin />} />
    </Routes>
  )
}

export default App

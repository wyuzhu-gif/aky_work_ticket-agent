import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import Review from './pages/review/Review'
import Report from './pages/report/Report'
import Dashboard from './pages/dashboard/Dashboard'
import TicketReview from './pages/ticketReview/TicketReview'
import SmartQuery from './pages/smartQuery/SmartQuery'
import PromptRules from './pages/rules/RulesPage'
import RuleDocManage from './pages/ruleDocs/RuleDocsPage'
import AgentAdmin from './pages/agentAdmin/AgentAdmin'
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

/** 审核看板 */
function DashboardPlaceholder() {
  return <Dashboard />
}

function Pages() {
  return (
    <Routes>
      {/* 工作台 */}
      <Route path="/" element={<DashboardPlaceholder />} />

      {/* 智能审核 */}
      <Route path="/review" element={<Review />} />
      <Route path="/review/:docId/report" element={<Report />} />
      <Route path="/rules" element={<PromptRules />} />

      {/* 作业票管理 */}
      <Route path="/ticket-review" element={<TicketReview />} />

      {/* 数据分析 */}
      <Route path="/smart-query" element={<SmartQuery />} />

      {/* 系统管理 */}
      <Route path="/agent-admin" element={<AgentAdmin />} />
      <Route path="/rule-docs" element={<RuleDocManage />} />
    </Routes>
  )
}

export default App

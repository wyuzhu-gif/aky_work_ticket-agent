import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import Files from "./pages/files/Files";
import Review from "./pages/review/Review";
import RuleLibrary from "./pages/ruleLibrary/RuleLibrary";
import Report from "./pages/report/Report";
import TicketDatabase from "./pages/ticketDatabase/TicketDatabase";
import SmartQuery from "./pages/smartQuery/SmartQuery";
import SqlAgentAdmin from "./pages/sqlagentAdmin/SqlAgentAdmin";
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
  );
}

function Pages() {
  return (
      <Routes>
          <Route path="/" element={<Files />} />
          <Route path="/rule-library" element={<RuleLibrary />} />
          <Route path="/review" element={<Review />} />
          <Route path="/report" element={<Report />} />
          <Route path="/ticket-database" element={<TicketDatabase />} />
          <Route path="/smart-query" element={<SmartQuery />} />
          <Route path="/sqlagent-admin" element={<SqlAgentAdmin />} />
      </Routes>
  );
}

export default App;

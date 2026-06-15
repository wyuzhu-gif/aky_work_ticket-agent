/**
 * Dashboard API — 审核看板聚合数据
 */
const API_BASE = import.meta.env.VITE_API_BASE || ''

export interface DashboardStats {
  total_reviews: number
  total_issues: number
  accepted_issues: number
  dismissed_issues: number
  pending_issues: number
  high_risk_issues: number
  total_permits: number
}

export interface RecentReview {
  doc_id: string
  issue_count: number
  high_risk_count: number
  accepted_count: number
  latest_review_time: string | null
}

export interface PermitTypeStat {
  type: string
  label: string
  count: number
}

export interface RiskDistribution {
  high: number
  medium: number
  low: number
  info: number
}

export interface DashboardResponse {
  stats: DashboardStats
  recent_reviews: RecentReview[]
  permit_type_stats: PermitTypeStat[]
  risk_distribution: RiskDistribution
}

export async function fetchDashboard(period: string = 'all'): Promise<DashboardResponse> {
  const res = await fetch(`${API_BASE}/api/v1/dashboard?period=${period}`)
  if (!res.ok) throw new Error(`Dashboard API error: ${res.status}`)
  return res.json()
}

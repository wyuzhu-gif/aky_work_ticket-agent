/**
 * 作业票（动火作业票）TypeScript 类型定义。
 */

export interface HotWorkPermit {
  id?: number
  permit_code: string
  work_id?: string

  apply_unit?: string
  apply_time?: string
  work_content?: string
  work_location?: string
  work_level?: string
  work_method?: string
  fire_worker_info?: string
  work_unit?: string
  work_owner_name?: string
  work_owner_phone?: string

  gas_analysis_time?: string
  gas_analyst_name?: string
  gas_analysis_result?: string

  related_permit_ids?: string
  risk_identification?: string

  start_time?: string
  end_time?: string

  safety_disclosure_person?: string
  safety_disclosure_time?: string
  accept_person?: string
  accept_time?: string
  attendant?: string

  approval_owner_opinion?: string
  approval_owner_sign?: string
  approval_owner_time?: string

  approval_unit_opinion?: string
  approval_unit_sign?: string
  approval_unit_time?: string

  approval_safety_opinion?: string
  approval_safety_sign?: string
  approval_safety_time?: string

  approval_fire_leader_opinion?: string
  approval_fire_leader_sign?: string
  approval_fire_leader_time?: string

  shift_leader_check_result?: string
  shift_leader_sign?: string
  shift_leader_time?: string

  completion_acceptance_result?: string
  completion_acceptance_sign?: string
  completion_acceptance_time?: string

  status?: string
  create_time?: string
}

export interface HotWorkGasAnalysis {
  id?: number
  permit_id?: number
  analysis_round?: number
  sample_time?: string
  representative_gas?: string
  analysis_result?: string
  analyst_name?: string
}

export interface ExtractedSafetyCheck {
  description: string
  is_confirmed: boolean
  confirmed_by?: string
}

export interface PermitUploadResponse {
  permit: HotWorkPermit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
  raw_md: string
}

export interface PermitSaveRequest {
  permit: HotWorkPermit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
}

export interface ComplianceReviewIssue {
  text: string
  field_key: string
  suggestion: string
}

export interface ComplianceReviewItem {
  category: string
  status: 'pass' | 'warning' | 'fail'
  issues: ComplianceReviewIssue[]
}

export interface ComplianceReviewRequest {
  permit: HotWorkPermit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
}

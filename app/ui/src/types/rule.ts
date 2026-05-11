export enum RiskLevel {
  High = '高',
  Medium = '中',
  Low = '低'
}

export enum RuleStatus {
  Active = 'active',
  Inactive = 'inactive'
}

export interface RuleExample {
  text: string
  explanation: string
}

export interface ReviewRule {
  id: string
  name: string
  description: string
  prompt: string | null
  folder_id: string | null
  risk_level: RiskLevel
  examples: RuleExample[]
  is_preset: boolean
  status: RuleStatus
  created_at: string
  updated_at?: string
}

export interface DocumentRuleAssociation {
  doc_id: string
  rule_id: string
  enabled: boolean
}

export interface CreateRuleRequest {
  name: string
  description: string
  prompt?: string | null
  folder_id?: string | null
  risk_level: RiskLevel
  examples?: RuleExample[]
}

export interface UpdateRuleRequest {
  name?: string
  description?: string
  prompt?: string | null
  folder_id?: string | null
  risk_level?: RiskLevel
  examples?: RuleExample[]
  status?: RuleStatus
}

export interface RuleFolder {
  id: string
  name: string
  description: string | null
  is_default: boolean
  created_at: string
  updated_at?: string
}

export interface CreateFolderRequest {
  name: string
  description?: string | null
}

export interface UpdateFolderRequest {
  name?: string
  description?: string | null
}

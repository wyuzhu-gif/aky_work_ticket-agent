"""fix_frontend_rule_types.py - Update rule.ts and RulesPanel.tsx and RuleLibrary.tsx"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src")

def write_file(rel_path: str, content: str):
    fp = BASE / rel_path
    fp.write_text(content, encoding="utf-8")
    print(f"  WROTE: {rel_path}")


# ========== types/rule.ts ==========
write_file("types/rule.ts", '''export enum RiskLevel {
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
  risk_level: RiskLevel
  examples?: RuleExample[]
}

export interface UpdateRuleRequest {
  name?: string
  description?: string
  prompt?: string | null
  risk_level?: RiskLevel
  examples?: RuleExample[]
  status?: RuleStatus
}
''')

print("Frontend types updated!")

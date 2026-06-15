export enum RuleDocumentSource {
  Context = 'context',
  Parsed = 'parsed',
}

export enum RuleDocumentStatus {
  Active = 'active',
  Inactive = 'inactive',
}

export interface RuleDocument {
  id: string
  name: string
  description?: string
  file_path: string
  file_type: string
  source_type: RuleDocumentSource
  extracted_text?: string
  parsed_rule_ids?: string[]
  status: RuleDocumentStatus
  created_at: string
  updated_at?: string
}

export interface DocumentRuleDocAssociation {
  doc_id: string
  rule_document_id: string
  enabled: boolean
}

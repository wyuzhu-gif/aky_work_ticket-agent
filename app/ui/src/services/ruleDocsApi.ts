// ========== Rule Documents API ==========
// Append these exports to the existing api.ts

import type { RuleDocument, DocumentRuleDocAssociation } from '../types/ruleDocument'

const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? ''
const ruleDocsApiUrl = `${apiOrigin}/api/v1/rule-documents`
const reviewApiUrl = `${apiOrigin}/api/v1/review`

class FatalError extends Error {
  constructor(message: string) { super(message); this.name = 'FatalError' }
}

async function getErrorMessage(response: Response): Promise<string> {
  let message = `接口错误（${response.statusText}）：`
  const errorText = await response.text()
  if (errorText) {
    try {
      const errorJson = JSON.parse(errorText)
      if (errorJson?.detail) {
        message += typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      } else if (errorJson?.message) {
        message += errorJson.message
      } else {
        message += '发生未知错误，请稍后重试。'
      }
    } catch {
      message += '发生未知错误，请稍后重试。'
    }
  } else {
    message += '发生未知错误，请稍后重试。'
  }
  return message
}

export async function getRuleDocuments(): Promise<RuleDocument[]> {
  const response = await fetch(ruleDocsApiUrl, { method: 'GET' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function uploadRuleDocument(file: File, description?: string): Promise<RuleDocument> {
  const formData = new FormData()
  formData.append('file', file)
  if (description) formData.append('description', description)
  const response = await fetch(`${ruleDocsApiUrl}/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function getRuleDocumentText(ruleDocId: string): Promise<{ id: string; name: string; extracted_text: string }> {
  const response = await fetch(`${ruleDocsApiUrl}/${ruleDocId}/text`, { method: 'GET' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function parseRuleDocument(ruleDocId: string): Promise<RuleDocument> {
  const response = await fetch(`${ruleDocsApiUrl}/${ruleDocId}/parse`, { method: 'POST' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function deleteRuleDocument(ruleDocId: string): Promise<void> {
  const response = await fetch(`${ruleDocsApiUrl}/${ruleDocId}`, { method: 'DELETE' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
}

export async function getDocumentRuleDocs(docId: string): Promise<DocumentRuleDocAssociation[]> {
  const response = await fetch(`${reviewApiUrl}/${docId}/rule-documents`, { method: 'GET' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function setDocumentRuleDoc(docId: string, ruleDocId: string, enabled: boolean): Promise<void> {
  const response = await fetch(`${reviewApiUrl}/${docId}/rule-documents/${ruleDocId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
}

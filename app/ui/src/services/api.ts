import { EventSourceMessage, fetchEventSource } from '@microsoft/fetch-event-source'
import { FatalError, RetriableError } from '../types/error'
import type { ReviewRule, CreateRuleRequest, UpdateRuleRequest, DocumentRuleAssociation } from '../types/rule'
import type { RuleFolder, CreateFolderRequest } from '../types/rule'

const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? ''
const apiBaseUrl = `${apiOrigin}/api/v1/review/`
const rulesApiUrl = `${apiOrigin}/api/v1/rules`
const foldersApiUrl = `${apiOrigin}/api/v1/rule-folders`
const unknownError = '发生未知错误，请稍后重试。'

class AbortedError extends Error {}

async function getErrorMessage(response: Response): Promise<string> {
  let message = `接口错误（${response.statusText}）：`
  const errorText = await response.text()
  if (errorText) {
    let errorJson
    try {
      errorJson = JSON.parse(errorText)
      if (errorJson?.detail) {
        message += typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      } else if (errorJson?.message) {
        message += errorJson.message
      } else {
        message += unknownError
      }
    } catch {
      message += unknownError
    }
  } else {
    message += unknownError
  }
  return message
}

export async function callApi(path: string, method = 'GET', body?: object) {
  const response = await fetch(apiBaseUrl + path, {
    headers: { 'Content-Type': 'application/json' },
    method,
    body: body ? JSON.stringify(body) : null
  })
  if (!response.ok) {
    const message = await getErrorMessage(response)
    if (response.status === 503) throw new RetriableError(message)
    else throw new FatalError(message)
  }
  return response
}

export async function streamApi(
  path: string,
  messageHandler: (msg: EventSourceMessage) => void,
  fatalErrorHandler: (err: Error) => void,
  abortControllerRef: AbortController,
  maxRetries = 3
) {
  let retries = 0
  async function startStream() {
    fetchEventSource(apiBaseUrl + path, {
      signal: abortControllerRef.signal,
      async onopen(response) {
        if (abortControllerRef.signal.aborted) throw new AbortedError()
        if (!response.ok) {
          const message = await getErrorMessage(response)
          if (response.status === 503) throw new RetriableError(message)
          else throw new FatalError(message)
        }
      },
      onmessage(msg) { messageHandler(msg) },
      onclose() {},
      onerror(err) {
        if (err instanceof RetriableError && retries < maxRetries) {
          retries++
          startStream()
        } else { throw err }
      }
    }).catch(fatalErrorHandler)
  }
  startStream()
}

// ========== Rules API ==========

export async function getRules(): Promise<ReviewRule[]> {
  const response = await fetch(rulesApiUrl, { headers: { 'Content-Type': 'application/json' }, method: 'GET' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function createRule(data: CreateRuleRequest): Promise<ReviewRule> {
  const response = await fetch(rulesApiUrl, {
    headers: { 'Content-Type': 'application/json' }, method: 'POST', body: JSON.stringify(data)
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function updateRule(ruleId: string, data: UpdateRuleRequest): Promise<ReviewRule> {
  const response = await fetch(`${rulesApiUrl}/${ruleId}`, {
    headers: { 'Content-Type': 'application/json' }, method: 'PATCH', body: JSON.stringify(data)
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function deleteRule(ruleId: string): Promise<void> {
  const response = await fetch(`${rulesApiUrl}/${ruleId}`, {
    headers: { 'Content-Type': 'application/json' }, method: 'DELETE'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
}

export async function getDocumentRules(docId: string): Promise<DocumentRuleAssociation[]> {
  const response = await fetch(`${apiBaseUrl}${docId}/rules`, {
    headers: { 'Content-Type': 'application/json' }, method: 'GET'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function setDocumentRule(docId: string, ruleId: string, enabled: boolean): Promise<void> {
  const response = await fetch(`${apiBaseUrl}${docId}/rules/${ruleId}`, {
    headers: { 'Content-Type': 'application/json' }, method: 'PUT', body: JSON.stringify({ enabled })
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
}

// ========== Folder API ==========

export async function getFolders(): Promise<RuleFolder[]> {
  const response = await fetch(foldersApiUrl, { headers: { 'Content-Type': 'application/json' }, method: 'GET' })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function createFolder(data: CreateFolderRequest): Promise<RuleFolder> {
  const response = await fetch(foldersApiUrl, {
    headers: { 'Content-Type': 'application/json' }, method: 'POST', body: JSON.stringify(data)
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function updateFolder(folderId: string, data: { name?: string; description?: string | null }): Promise<RuleFolder> {
  const response = await fetch(`${foldersApiUrl}/${folderId}`, {
    headers: { 'Content-Type': 'application/json' }, method: 'PATCH', body: JSON.stringify(data)
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function deleteFolder(folderId: string): Promise<void> {
  const response = await fetch(`${foldersApiUrl}/${folderId}`, {
    headers: { 'Content-Type': 'application/json' }, method: 'DELETE'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
}

export async function setDefaultFolder(folderId: string): Promise<RuleFolder> {
  const response = await fetch(`${foldersApiUrl}/${folderId}/default`, {
    headers: { 'Content-Type': 'application/json' }, method: 'PUT'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function getDefaultFolder(): Promise<RuleFolder | null> {
  const response = await fetch(`${foldersApiUrl}/default`, {
    headers: { 'Content-Type': 'application/json' }, method: 'GET'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  const data = await response.json()
  return data.default_folder
}

export async function getFolderRules(folderId: string): Promise<ReviewRule[]> {
  const response = await fetch(`${foldersApiUrl}/${folderId}/rules`, {
    headers: { 'Content-Type': 'application/json' }, method: 'GET'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

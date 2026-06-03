/**
 * SmartQuery 会话历史 API
 */
const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? ''

export interface SessionInfo {
  id: string
  title: string
  created_at: string
  updated_at: string
  msg_count?: number
}

export interface SessionMessage {
  id: number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  queryData?: {
    columns: string[]
    data: Record<string, unknown>[]
    sql: string
  } | null
  chartConfig?: Record<string, unknown> | null
  thinkingSteps?: Array<{
    action: string
    tool_name: string
    status: 'preparing' | 'running' | 'completed'
    duration_ms?: number
  }> | null
  created_at: string
}

export async function listSessions(limit = 50, offset = 0): Promise<SessionInfo[]> {
  const resp = await fetch(`${apiOrigin}/api/v1/chat/sessions?limit=${limit}&offset=${offset}`)
  if (!resp.ok) throw new Error('获取会话列表失败')
  const json = await resp.json()
  return json.data ?? []
}

export async function createSession(title = ''): Promise<SessionInfo> {
  const resp = await fetch(`${apiOrigin}/api/v1/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!resp.ok) throw new Error('创建会话失败')
  const json = await resp.json()
  return json.data
}

export async function getSession(sessionId: string): Promise<{ session: SessionInfo; messages: SessionMessage[] }> {
  const resp = await fetch(`${apiOrigin}/api/v1/chat/sessions/${sessionId}`)
  if (!resp.ok) throw new Error('获取会话详情失败')
  const json = await resp.json()
  return json.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await fetch(`${apiOrigin}/api/v1/chat/sessions/${sessionId}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error('删除会话失败')
}

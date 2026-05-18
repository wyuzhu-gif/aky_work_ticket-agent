export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  thinkingSteps?: ThinkingStep[]
  queryData?: QueryData
  chartConfig?: Record<string, unknown>
}

export interface ThinkingStep {
  action: string
  tool_name: string
  status: 'preparing' | 'running' | 'completed'
  duration_ms?: number
}

export interface QueryData {
  columns: string[]
  data: Record<string, unknown>[]
  sql: string
}

interface SSEEvent {
  type: string
  [key: string]: unknown
}

/**
 * Parse completed SSE events from a buffer.
 * Returns { events, remaining } where remaining is unparsed partial data.
 */
function parseSSEBuffer(buffer: string): { events: SSEEvent[]; remaining: string } {
  const events: SSEEvent[] = []
  // SSE events are delimited by \n\n
  const parts = buffer.split('\n\n')
  // The last part might be incomplete (no trailing \n\n yet), keep it as remaining
  const remaining = parts.pop() ?? ''

  for (const part of parts) {
    for (const line of part.split('\n')) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          events.push(JSON.parse(trimmed.slice(6)))
        } catch { /* skip malformed JSON */ }
      }
    }
  }
  return { events, remaining }
}

export async function streamChat(
  question: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const resp = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  if (!resp.body) throw new Error('No response body')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { events, remaining } = parseSSEBuffer(buffer)
    buffer = remaining
    for (const ev of events) onEvent(ev)
  }
  // Parse any remaining data
  if (buffer.trim()) {
    const { events } = parseSSEBuffer(buffer + '\n\n')
    for (const ev of events) onEvent(ev)
  }
}

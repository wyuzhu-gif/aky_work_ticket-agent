/**
 * Agent 网关 API (FastAPI 业务网关 → Hermes Gateway)
 *
 * 历史:
 *   - 2026-06-25 之前: hermesChat() → POST /api/v1/hermes-chat (subprocess 阻塞)
 *   - 2026-06-25: 迁移到 POST /api/v1/agent/chat (FastAPI 业务网关 → Hermes Gateway HTTP)
 *
 * 关键变化:
 *   1. URL: /api/v1/hermes-chat → /api/v1/agent/chat
 *   2. 协议: 一次性 JSON → SSE 流式 (SSE 块字节级透传)
 *   3. 支持取消: agentCancel(traceId) 调 /api/v1/agent/chat/cancel
 *   4. 支持 skills 选择: 默认 ["ticket-nl2sql"], 可切 ["llm-wiki"]
 *
 * 协议细节 (跟 OpenAI 兼容):
 *   请求: { model, messages, stream, skills }
 *   响应: text/event-stream, 每行 "data: {json}\n\n", 终止 "data: [DONE]\n\n"
 *   错误: "event: error\ndata: {json}\n\n"
 */
import { getSkills } from './agentSkillsApi'

export interface AgentChatRequest {
  question: string
  /** 加载的 skills, 默认 ['ticket-nl2sql']; 也可传 ['llm-wiki'] */
  skills?: string[]
  /** 覆盖默认模型 */
  model?: string
  /** 会话 ID: 已有会话则追加消息, 不传则后端自动创建新会话 */
  sessionId?: string
}

export interface AgentChunkDelta {
  /** OpenAI 协议 chunk, 通常 choices[0].delta.content */
  content?: string
  role?: string
}

export interface AgentChatHandlers {
  /** 每收到一个 SSE data 行触发 */
  onDelta?: (delta: AgentChunkDelta, raw: string) => void
  /** 正常完成触发 (收到 [DONE] 或 finish_reason=stop) */
  onDone?: (meta: { totalContent: string; traceId: string }) => void
  /** 错误触发 (event: error 行 或 网络异常) */
  onError?: (err: Error) => void
  /** 拿到 trace_id 时触发 (从响应头 X-Request-ID) */
  onTraceId?: (traceId: string) => void
  /**
   * 后端在流开始时推的 metadata 事件 (含 session_id)
   * 前端拿到后保存 currentSessionId
   */
  onMetadata?: (meta: { sessionId?: string; traceId?: string; taskId?: string }) => void
  /**
   * 后端从 LLM 输出里抽到 chartconfig 块, 推过来
   * 触发时机: 流式结束后, 最后一个 data 帧之后
   * payload: chart.js 完整配置 (type/title/data/options/...)
   */
  onChart?: (config: Record<string, unknown>, cleanedText: string) => void
  /**
   * 后端 stream guard 收尾推的统一 schema (Phase 2, 2026-06-25)
   * 触发时机: finally 块, 永远会推 (即使失败)
   * payload.type: 'qa' | 'analytics' - 跟智能问数 SmartQuery 对齐
   * payload.answer: 完整或 partial 文本
   * payload.chart_config: 可选
   * payload.partial: true 表示被截断 (stream guard 启动)
   */
  onResponse?: (payload: AgentResponsePayload) => void
}

export interface AgentResponsePayload {
  type: 'qa' | 'analytics'
  answer: string
  chart_config?: Record<string, unknown> | null
  trace_id?: string
  finished_normally: boolean
  partial: boolean
}

export interface AgentChatHandle {
  /** 主动取消 (abort fetch + 通知后端 cancel) */
  abort: () => void
  /** 服务端 trace_id, 透传给 hermes 用于审计 */
  traceId: string
  /** 服务端 task_id, 取消 + 资源清理用的稳定 key (Phase 1, 2026-06-25) */
  taskId: string
}

/**
 * 流式调 agent 问答
 *
 * 用 fetch + ReadableStream 解析 SSE, 不依赖 EventSource (后者不支持 POST body)
 */
export async function agentChatStream(
  req: AgentChatRequest,
  handlers: AgentChatHandlers = {},
): Promise<AgentChatHandle> {
  const abortCtrl = new AbortController()
  let traceId = ''
  let taskId = ''
  let totalContent = ''

  // 防御: 拉一次 skills 白名单, 避免前端传非法 skill 触发 400
  let allowedSkills: string[] = []
  try {
    const skillsResp = await getSkills()
    allowedSkills = skillsResp.skills.map(s => s.name)
  } catch {
    // 拉不到也继续, 服务端会校验
  }

  const requestedSkills = (req.skills && req.skills.length > 0)
    ? req.skills
    : ['ticket-nl2sql']
  const finalSkills = allowedSkills.length === 0
    ? requestedSkills
    : requestedSkills.filter(s => allowedSkills.includes(s))

  // 发起请求
  let resp: Response
  try {
    resp = await fetch('/api/v1/agent/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: req.model ?? 'hermes',
        messages: [{ role: 'user', content: req.question }],
        stream: true,
        skills: finalSkills,
        ...(req.sessionId ? { session_id: req.sessionId } : {}),
      }),
      signal: abortCtrl.signal,
    })
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      // 用户主动取消, 不算错
      return makeHandle(abortCtrl, traceId, taskId)
    }
    handlers.onError?.(new Error('网络错误: ' + (e?.message || String(e))))
    return makeHandle(abortCtrl, traceId, taskId)
  }

  // 拿 trace_id 和 task_id (服务端响应头)
  // 关键: task_id 是 cancel 用的稳定 key (前端 refresh 也能用)
  const respTrace = resp.headers.get('X-Request-ID') || resp.headers.get('x-request-id') || ''
  if (respTrace) {
    traceId = respTrace
    handlers.onTraceId?.(respTrace)
  }
  const respTask = resp.headers.get('X-Task-ID') || resp.headers.get('x-task-id') || ''
  if (respTask) {
    taskId = respTask
  }

  if (!resp.ok) {
    let detail = ''
    try { detail = (await resp.text()).slice(0, 500) } catch { /* ignore */ }
    handlers.onError?.(new Error('HTTP ' + resp.status + ': ' + (detail || resp.statusText)))
    return makeHandle(abortCtrl, traceId, taskId)
  }

  if (!resp.body) {
    handlers.onError?.(new Error('响应无 body (浏览器不支持 ReadableStream)'))
    return makeHandle(abortCtrl, traceId, taskId)
  }

  // 异步消费 SSE, 不 await (fire-and-forget)
  consumeSse(resp.body, abortCtrl, handlers, totalContent, traceId)
    .catch(() => { /* 错误已在 handlers.onError 处理 */ })

  return makeHandle(abortCtrl, traceId, taskId)
}

function makeHandle(abortCtrl: AbortController, traceId: string, taskId: string): AgentChatHandle {
  // abort = 前端 abort fetch + 主动通知后端 cancel (Phase 1, 2026-06-25)
  // 关键: 浏览器 refresh 时 fetch 自动 abort, 但我们也要确保业务网关 + hermes 也停
  // 否则 hermes 内部 task 永远在跑 (zombie)
  let aborted = false
  return {
    abort: () => {
      if (aborted) return
      aborted = true
      try {
        abortCtrl.abort()
      } catch { /* ignore */ }
      // 同步调 /cancel 端点 (fire-and-forget)
      // task_id 优先 (Phase 1 新协议), 没有则 fallback trace_id (Phase 0 兼容)
      const id = taskId || traceId
      if (!id) return
      const body = taskId ? { task_id: taskId } : { trace_id: traceId }
      fetch('/api/v1/agent/chat/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch(() => {
        // 取消失败是 best-effort, 不抛错
      })
    },
    get traceId() { return traceId },
    get taskId() { return taskId },
  } as AgentChatHandle
}

async function consumeSse(
  body: ReadableStream<Uint8Array>,
  abortCtrl: AbortController,
  handlers: AgentChatHandlers,
  _initialContent: string,
  traceId: string,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let totalContent = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 协议: 事件以 \n\n 分隔
      let sep = buffer.indexOf('\n\n')
      while (sep >= 0) {
        const eventBlock = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const more = parseAndDispatch(eventBlock, handlers, traceId, totalContent)
        if (more !== null) totalContent = more
        sep = buffer.indexOf('\n\n')
      }
    }
    if (buffer.trim()) {
      const more = parseAndDispatch(buffer, handlers, traceId, totalContent)
      if (more !== null) totalContent = more
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') return  // 用户主动取消
    handlers.onError?.(new Error('流式读取失败: ' + (e?.message || String(e))))
    return
  }
  handlers.onDone?.({ totalContent, traceId })
}

/**
 * 解析单个 SSE event block, 触发对应 handler
 * 返回: 新的 totalContent (如果 chunk 含 content), 或 null (无变更)
 */
function parseAndDispatch(
  eventBlock: string,
  handlers: AgentChatHandlers,
  traceId: string,
  totalContent: string,
): string | null {
  const lines = eventBlock.split('\n')
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  const data = dataLines.join('\n')
  if (!data) return null

  if (data === '[DONE]') {
    handlers.onDone?.({ totalContent, traceId })
    return null
  }

  if (eventName === 'error') {
    let msg = data
    try {
      const obj = JSON.parse(data)
      msg = obj?.error?.message || obj?.message || data
    } catch { /* keep raw */ }
    handlers.onError?.(new Error(String(msg)))
    return null
  }

  if (eventName === 'metadata') {
    // 后端在流开始时推的 metadata 事件 (含 session_id)
    try {
      const obj = JSON.parse(data) as {
        session_id?: string
        trace_id?: string
        task_id?: string
      }
      handlers.onMetadata?.({
        sessionId: obj.session_id,
        traceId: obj.trace_id,
        taskId: obj.task_id,
      })
    } catch { /* ignore parse error */ }
    return null
  }

  if (eventName === 'chart') {
    // chartconfig 块: { config: {...}, cleaned_text: "..." }
    try {
      const obj = JSON.parse(data)
      const cfg = obj?.config
      if (cfg && typeof cfg === 'object') {
        const cleaned = typeof obj.cleaned_text === 'string' ? obj.cleaned_text : ''
        handlers.onChart?.(cfg, cleaned)
      }
    } catch (e) {
      handlers.onError?.(new Error('chart event 解析失败: ' + (e as Error).message))
    }
    return null
  }

  if (eventName === 'response') {
    // 统一 schema 收尾 (Phase 2)
    // { type, answer, chart_config, trace_id, finished_normally, partial }
    try {
      const obj = JSON.parse(data) as {
        type?: string
        answer?: string
        chart_config?: Record<string, unknown> | null
        trace_id?: string
        finished_normally?: boolean
        partial?: boolean
      }
      handlers.onResponse?.({
        type: (obj.type === 'analytics' ? 'analytics' : 'qa'),
        answer: typeof obj.answer === 'string' ? obj.answer : '',
        chart_config: obj.chart_config ?? null,
        trace_id: obj.trace_id,
        finished_normally: obj.finished_normally !== false,
        partial: obj.partial === true,
      })
    } catch (e) {
      handlers.onError?.(new Error('response event 解析失败: ' + (e as Error).message))
    }
    return null
  }

  if (eventName === 'done') {
    // stream guard 收尾 (永远 emit)
    // { trace_id, finished_normally, has_content, has_chart }
    // 这里 onDone 是给用户的"完成"信号, 但数据已在 onDelta/onChart/onResponse 推完
    return null
  }

  // 普通 chunk: OpenAI 协议
  try {
    const obj = JSON.parse(data)
    const delta = obj?.choices?.[0]?.delta
    if (delta) {
      if (typeof delta.content === 'string' && delta.content.length > 0) {
        totalContent += delta.content
      }
      handlers.onDelta?.(delta, data)
      return totalContent
    }
  } catch { /* 非 JSON 忽略 */ }
  return null
}

/**
 * 主动取消正在生成的 LLM 响应 (server-side cancel, 2026-06-25 Phase 1)
 *
 * 优先用 task_id (Phase 1 新协议), fallback trace_id (Phase 0 兼容).
 * 通常在 React 组件里直接调 handle.abort() 即可, 不必显式调这个.
 */
export async function agentCancel(opts: { taskId?: string; traceId?: string }): Promise<{ status: string }> {
  const { taskId, traceId } = opts
  if (!taskId && !traceId) return { status: 'no_id' }
  try {
    const body = taskId ? { task_id: taskId } : { trace_id: traceId! }
    const resp = await fetch('/api/v1/agent/chat/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) {
      return { status: 'http_' + resp.status }
    }
    return await resp.json()
  } catch {
    return { status: 'network_error' }
  }
}

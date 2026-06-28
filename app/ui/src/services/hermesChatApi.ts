/**
 * ⚠️ 2026-06-25: 这个文件已废弃, 仅作 re-export 兼容
 * 真正的实现迁移到了 agentChatApi.ts (FastAPI 业务网关 → Hermes Gateway HTTP)
 *
 * 历史:
 *   - 之前: hermesChat() → POST /api/v1/hermes-chat (subprocess 阻塞)
 *   - 现在: agentChatStream() → POST /api/v1/agent/chat (SSE 流式, 后端透传 Hermes Gateway)
 *
 * 推荐: 直接 import { agentChatStream } from './agentChatApi'
 */
export { agentChatStream, agentCancel } from './agentChatApi'
export type { AgentChatRequest, AgentChatHandlers, AgentChatHandle, AgentChunkDelta } from './agentChatApi'

/** @deprecated 用 agentChatStream 替代 */
export interface HermesChatRequest {
  question: string
  timeout?: number
}

/** @deprecated 用 AgentChatHandle 替代 */
export interface HermesChatResponse {
  question: string
  answer: string
  elapsed_seconds?: number
  chart_config?: Record<string, unknown> | null
}

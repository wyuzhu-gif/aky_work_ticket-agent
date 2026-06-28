/** 智能问数 + hermes 问答共用的聊天数据类型 */

export interface ThinkingStep {
  action: string
  tool_name: string
  status: 'preparing' | 'running' | 'completed'
  duration_ms?: number
  result?: string
  update?: boolean
}

export interface QueryData {
  columns: string[]
  data: Record<string, unknown>[]
  sql: string
}

/** 知识引用: 每个页面返回 filepath/title/snippet/content */
export interface WikiRef {
  filepath: string
  title: string
  snippet: string
  content?: string     // 展开时加载全文
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  thinkingSteps?: ThinkingStep[]
  queryData?: QueryData
  chartConfig?: Record<string, unknown>
  wikiResults?: WikiRef[]
}

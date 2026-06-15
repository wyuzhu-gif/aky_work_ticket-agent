const BASE = '/api/v1/sqlagent'

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v) })
  const resp = await fetch(`${BASE}${path.startsWith('/') ? path : '/' + path}${url.search ? '?' + url.searchParams.toString() : ''}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `HTTP ${resp.status}`)
  }
  return resp.json()
}

// ── LLM Config ──
export interface LLMConfig {
  api_key: string
  base_url: string
  model_name: string
  temperature: number
  max_tokens: number
}

export const getLLMConfig = () => request<{ configured: boolean } & Partial<LLMConfig>>('GET', '/llm-config')
export const setLLMConfig = (cfg: LLMConfig) => request('PUT', '/llm-config', cfg)
export const testLLM = (cfg: LLMConfig) => request<{ success: boolean; message: string }>('POST', '/llm-test', cfg)

// ── DB Config ──
export interface DBConfig {
  db_type: string
  host: string
  port: number
  dbname: string
  username: string
  password: string
}

export const getDBConfig = () => request<{ configured: boolean } & Partial<DBConfig>>('GET', '/db-config')
export const setDBConfig = (cfg: DBConfig) => request('PUT', '/db-config', cfg)
export const testDB = (cfg: DBConfig) => request<{ success: boolean; message: string }>('POST', '/db-test', cfg)

// ── Training Data ──
export interface TrainingItem {
  id: string
  training_data_type: string
  question?: string
  content?: string
  sql?: string
}

export const getTrainingData = (training_type?: string) =>
  request<{ data: TrainingItem[]; total: number }>('GET', '/training', undefined, training_type ? { training_type } : undefined)
export const addTrainingData = (data: { training_type: string; content?: string; question?: string; sql?: string }) =>
  request('POST', '/training/add', data)
export const deleteTrainingData = (item_id: string) =>
  request('DELETE', `/training/${item_id}`)

// ── Agent Config ──
export interface AgentConfig {
  greeting: string
  example_questions: string[]
  custom_prompt: string
}

export const getAgentConfig = () => request<AgentConfig>('GET', '/agent-config')
export const setAgentConfig = (cfg: AgentConfig) => request('PUT', '/agent-config', cfg)

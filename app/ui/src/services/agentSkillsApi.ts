/**
 * Agent Skills API - 拉可用 skills 白名单
 *
 * 后端: GET /api/v1/agent/skills
 * 返: { skills: [{ name, desc, category, allowed }], default: string | null }
 */

export interface AgentSkill {
  name: string
  desc: string
  category: string
  allowed: boolean
}

export interface AgentSkillsResponse {
  skills: AgentSkill[]
  default: string | null
}

let _cache: AgentSkillsResponse | null = null
let _cacheTime = 0
const CACHE_TTL_MS = 60_000  // 1 分钟缓存

export async function getSkills(): Promise<AgentSkillsResponse> {
  const now = Date.now()
  if (_cache && now - _cacheTime < CACHE_TTL_MS) {
    return _cache
  }
  try {
    const resp = await fetch('/api/v1/agent/skills')
    if (!resp.ok) {
      throw new Error('HTTP ' + resp.status)
    }
    const data = await resp.json() as AgentSkillsResponse
    _cache = data
    _cacheTime = now
    return data
  } catch (e) {
    // 降级: 返回前端已知的硬编码列表
    return {
      skills: [
        { name: 'ticket-nl2sql', desc: '作业票业务库自然语言查询', category: 'data', allowed: true },
        { name: 'llm-wiki', desc: '全局知识库检索 (作业票/法规/审查)', category: 'knowledge', allowed: true },
      ],
      default: 'ticket-nl2sql',
    }
  }
}

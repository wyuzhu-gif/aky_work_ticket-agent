/**
 * 作业票 API 客户端 - 支持多种作业票类型。
 */

import type { HotWorkPermit, HotWorkGasAnalysis, ComplianceReviewItem } from '../types/permit'

const BASE = (import.meta.env.VITE_API_ORIGIN ?? '') + '/api/v1/permits'
const TYPES_BASE = (import.meta.env.VITE_API_ORIGIN ?? '') + '/api/v1/permit-types'
const DRAFTS_BASE = (import.meta.env.VITE_API_ORIGIN ?? '') + '/api/v1/drafts'

async function parse<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const detail = await resp.text()
    throw new Error(detail)
  }
  return resp.json()
}

/** 获取支持的作业票类型 */
export async function getPermitTypes(): Promise<{ key: string; label: string }[]> {
  const resp = await fetch(TYPES_BASE)
  return parse(resp)
}

/** 上传 PDF → MinerU + LLM 提取结构化数据 */
export async function uploadAndExtract(file: File, permitType: string = 'hot_work'): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${BASE}/upload-and-extract?permit_type=${permitType}`, { method: 'POST', body: form })
  return parse(resp)
}

/** 确认保存到数据库 */
export async function savePermit(data: {
  permit_type: string
  permit: Record<string, any>
  gas_analyses: Record<string, any>[]
  safety_checks: Record<string, any>[]
}): Promise<{ id: number; code: string }> {
  const resp = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return parse(resp)
}

/** 查询作业票列表 */
export async function listPermits(permitType: string = 'hot_work'): Promise<any[]> {
  const resp = await fetch(`${BASE}?permit_type=${permitType}`)
  return parse(resp)
}

/** 获取单张详情 */
export async function getPermit(id: number, permitType: string = 'hot_work'): Promise<any> {
  const resp = await fetch(`${BASE}/${id}?permit_type=${permitType}`)
  return parse(resp)
}

/** 合规性审查 */
export async function complianceReview(data: {
  permit_type: string
  data: Record<string, any>
}): Promise<ComplianceReviewItem[]> {
  const resp = await fetch(`${BASE}/compliance-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return parse<ComplianceReviewItem[]>(resp)
}

/** Hermes AI 审查 (调 hermes subprocess + llm-wiki) */
export interface HermesReviewResponse {
  ok: boolean
  results?: ComplianceReviewItem[]
  parse_method?: string
  elapsed?: number
  raw_output?: string
  raw_preview?: string
  error?: string
}

export async function hermesReview(data: {
  permit_type: string
  permit: Record<string, any>
  gas_analyses?: any[]
  safety_checks?: any[]
}): Promise<HermesReviewResponse> {
  const resp = await fetch(`${BASE}/hermes/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return parse<HermesReviewResponse>(resp)
}

/** Hermes 预热 (启动 hermes 进程, 提前加载 LLM) */
export async function hermesWarmup(): Promise<{ status: string; elapsed: number }> {
  const resp = await fetch(`${BASE}/hermes/warmup`, { method: 'POST' })
  return parse<{ status: string; elapsed: number }>(resp)
}

/** Hermes 状态 (前端轮询: 是否可用) */
export async function hermesStatus(): Promise<{ available: boolean; hermes_bin: string }> {
  const resp = await fetch(`${BASE}/hermes/status`)
  return parse<{ available: boolean; hermes_bin: string }>(resp)
}

/** 删除 */
export async function deletePermit(id: number, permitType: string = 'hot_work'): Promise<void> {
  await fetch(`${BASE}/${id}?permit_type=${permitType}`, { method: 'DELETE' })
}

// ──────────── 2026-06-22: 草稿 (暂存 / 保存到本地) ────────────

export interface DraftSummary {
  permit_code: string
  permit_type: string
  permit_unit?: string
  permit_location?: string
  permit_job?: string
  gas_count: number
  safety_count: number
  has_review: boolean
  review_count: number
  created_at?: string
  updated_at?: string
}

export interface DraftDetail extends Omit<DraftSummary, 'permit_unit' | 'permit_location' | 'permit_job' | 'gas_count' | 'safety_count' | 'review_count'> {
  permit: Record<string, any>
  gas_analyses: any[]
  safety_checks: any[]
  review_results: ComplianceReviewItem[]
}

/** 暂存 / 保存到本地 (upsert, 后端按 permit_code 覆盖) */
export async function saveDraft(data: {
  permit_code: string
  permit_type: string
  permit: Record<string, any>
  gas_analyses?: any[]
  safety_checks?: any[]
  review_results?: ComplianceReviewItem[]
}): Promise<DraftSummary> {
  const resp = await fetch(DRAFTS_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return parse<DraftSummary>(resp)
}

/** 列草稿 (元信息, 不含大 JSON) */
export async function listDrafts(permitType?: string): Promise<DraftSummary[]> {
  const q = permitType ? `?permit_type=${encodeURIComponent(permitType)}` : ''
  const resp = await fetch(`${DRAFTS_BASE}${q}`)
  return parse<DraftSummary[]>(resp)
}

/** 加载单个草稿 (含 permit + gas + safety + review 完整) */
export async function getDraft(permitCode: string): Promise<DraftDetail> {
  const resp = await fetch(`${DRAFTS_BASE}/${encodeURIComponent(permitCode)}`)
  return parse<DraftDetail>(resp)
}

/** 删除草稿 */
export async function deleteDraft(permitCode: string): Promise<void> {
  await fetch(`${DRAFTS_BASE}/${encodeURIComponent(permitCode)}`, { method: 'DELETE' })
}

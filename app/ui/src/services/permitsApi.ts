/**
 * 作业票 API 客户端 - 支持多种作业票类型。
 */

import type { HotWorkPermit, HotWorkGasAnalysis, ComplianceReviewItem } from '../types/permit'

const BASE = (import.meta.env.VITE_API_ORIGIN ?? '') + '/api/v1/permits'
const TYPES_BASE = (import.meta.env.VITE_API_ORIGIN ?? '') + '/api/v1/permit-types'

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

/** 删除 */
export async function deletePermit(id: number, permitType: string = 'hot_work'): Promise<void> {
  await fetch(`${BASE}/${id}?permit_type=${permitType}`, { method: 'DELETE' })
}

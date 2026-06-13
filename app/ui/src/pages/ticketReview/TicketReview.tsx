/**
 * 作业票审查页面 - GB 30871-2022 八类作业票。
 *
 * 设计：
 * - 8 类票下拉框（动态从后端拉取）
 * - 每类票的字段定义（FIELDS_BASIC/..._TIME/..._GAS/..._RELATED/..._DISCLOSURE/
 *   4-7 段审批/动火前/完工/吊装/动土/断路 等 section）独立配置
 * - 切换票种时表单字段自动切换；列表清空
 * - 不入库：暂存到 localStorage，确认按钮只触发审查
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge,
  Button,
  Dialog,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  Input,
  Label,
  makeStyles,
  Dropdown,
  Option,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Text,
  Textarea,
  tokens,
  Divider,
  Checkbox,
} from '@fluentui/react-components'
import {
  ArrowUploadRegular,
  DeleteRegular,
  DatabaseRegular,
  SaveRegular,
  DismissRegular,
  ShieldCheckmarkRegular,
  ArrowRedoRegular,
  CheckmarkRegular,
} from '@fluentui/react-icons'
import type {
  HotWorkPermit,
  HotWorkGasAnalysis,
  ExtractedSafetyCheck,
  PermitUploadResponse,
  ComplianceReviewItem,
} from '../../types/permit'
import {
  uploadAndExtract,
  savePermit,
  listPermits,
  getPermit,
  deletePermit,
  complianceReview,
  getPermitTypes,
} from '../../services/permitsApi'

// ──────────────── Styles ────────────────

const useStyles = makeStyles({
  container: { display: 'flex', flexDirection: 'column', gap: '24px' },
  title: { fontSize: '20px', fontWeight: 700, color: tokens.colorBrandForeground1 },

  mainLayout: {
    display: 'grid',
    gridTemplateColumns: '1fr',
    gap: '24px',
    transitionProperty: 'grid-template-columns',
    transitionDuration: '300ms',
  },
  mainLayoutWithReview: {
    gridTemplateColumns: '1fr 380px',
  },

  formSide: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
    minWidth: 0,
  },

  reviewPanel: {
    position: 'sticky' as const,
    top: '80px',
    maxHeight: 'calc(100vh - 100px)',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    padding: '16px',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    backgroundColor: tokens.colorNeutralBackground1,
  },
  reviewHeader: {
    fontSize: '16px',
    fontWeight: 700,
    color: tokens.colorBrandForeground1,
    marginBottom: '4px',
  },
  reviewSummary: { display: 'flex', gap: '12px', marginBottom: '8px' },
  reviewCategory: {
    padding: '10px 0',
    borderBottom: `1px solid ${tokens.colorNeutralStroke3}`,
    '&:last-child': { borderBottom: 'none' },
  },
  categoryHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '6px',
  },
  statusBadge: {
    fontSize: '12px',
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: '4px',
  },
  statusPass: { backgroundColor: '#e2f9e2', color: '#1a7a1a' },
  statusWarn: { backgroundColor: '#fff4ce', color: '#9d5d00' },
  statusFail: { backgroundColor: '#fde7e9', color: '#c4314b' },
  issueItem: {
    padding: '8px 10px',
    marginBottom: '6px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground1Hover,
    cursor: 'pointer',
    border: '1px solid transparent',
    transitionProperty: 'border-color, background-color',
    transitionDuration: '150ms',
    '&:hover': {
      borderColor: tokens.colorBrandStroke1,
      backgroundColor: tokens.colorBrandBackground2,
    },
  },
  issueText: { fontSize: '13px', color: tokens.colorNeutralForeground1, lineHeight: '20px' },
  issueSuggestion: { fontSize: '12px', color: tokens.colorBrandForeground1, marginTop: '4px', lineHeight: '18px' },
  issueFieldTag: {
    display: 'inline-block',
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
    backgroundColor: tokens.colorNeutralBackground4,
    padding: '1px 6px',
    borderRadius: '3px',
    marginTop: '4px',
  },

  uploadZone: {
    border: `2px dashed ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    padding: '40px',
    textAlign: 'center',
    cursor: 'pointer',
    transitionProperty: 'border-color, background-color',
    transitionDuration: '200ms',
    '&:hover': {
      borderColor: tokens.colorBrandStroke1,
      backgroundColor: tokens.colorBrandBackground2,
    },
  },
  uploadIcon: { fontSize: '36px', color: tokens.colorBrandForeground1, marginBottom: '12px' },
  uploadText: { color: tokens.colorNeutralForeground3, fontSize: '14px' },

  formSection: {
    padding: '20px',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    transitionProperty: 'border-color, box-shadow',
    transitionDuration: '300ms',
  },
  formSectionHighlight: {
    borderColor: tokens.colorBrandStroke1,
    boxShadow: `0 0 0 2px ${tokens.colorBrandBackground2}`,
  },
  sectionTitle: {
    fontSize: '15px',
    fontWeight: 600,
    color: tokens.colorBrandForeground1,
    marginBottom: '12px',
  },
  fieldGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '12px',
  },
  fieldItem: { display: 'flex', flexDirection: 'column', gap: '4px' },
  fieldLabel: { fontSize: '12px', color: tokens.colorNeutralForeground3, fontWeight: 500 },
  actions: { display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '8px', flexWrap: 'wrap' as const },
  tableWrap: { overflowX: 'auto' },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    padding: '60px',
    color: tokens.colorNeutralForeground3,
  },
  emptyIcon: { fontSize: '48px', opacity: 0.5 },
  draftRow: { cursor: 'pointer', '&:hover': { backgroundColor: tokens.colorNeutralBackground1Hover } },
})

// ──────────────── Field definitions per permit type ────────────────

/** 通用字段：编号/申请单位/时间/内容/地点/级别/方式/作业人员/作业单位/作业负责人/联系方式 */
const COMMON_BASIC: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'work_level', label: '作业级别' },
  { key: 'work_method', label: '作业方式' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
]

const FIELDS_TIME: FieldDef[] = [
  { key: 'start_time', label: '作业开始时间' },
  { key: 'end_time', label: '作业结束时间' },
]

const FIELDS_RELATED: FieldDef[] = [
  { key: 'related_permit_ids', label: '关联的其他特殊作业票证' },
  { key: 'risk_identification', label: '安全风险辨识结果', multiline: true },
]

const FIELDS_DISCLOSURE: FieldDef[] = [
  { key: 'safety_disclosure_person', label: '安全交底人' },
  { key: 'safety_disclosure_time', label: '交底时间' },
  { key: 'accept_person', label: '接受交底人' },
  { key: 'accept_time', label: '接受时间' },
  { key: 'attendant', label: '监护人' },
]

const FIELDS_GAS_OVERVIEW: FieldDef[] = [
  { key: 'gas_analysis_time', label: '气体取样分析时间' },
  { key: 'gas_analyst_name', label: '分析人' },
  { key: 'gas_analysis_result', label: '分析结果' },
]

const FIELDS_APPROVAL_OWNER: FieldDef[] = [
  { key: 'approval_owner_opinion', label: '作业负责人意见' },
  { key: 'approval_owner_sign', label: '作业负责人签字' },
  { key: 'approval_owner_time', label: '签字时间' },
]

const FIELDS_APPROVAL_UNIT: FieldDef[] = [
  { key: 'approval_unit_opinion', label: '所在单位意见' },
  { key: 'approval_unit_sign', label: '所在单位签字' },
  { key: 'approval_unit_time', label: '签字时间' },
]

const FIELDS_APPROVAL_SAFETY: FieldDef[] = [
  { key: 'approval_safety_opinion', label: '安全管理部门意见' },
  { key: 'approval_safety_sign', label: '安全管理部门签字' },
  { key: 'approval_safety_time', label: '签字时间' },
]

const FIELDS_APPROVAL_SUPERVISOR: FieldDef[] = [
  { key: 'approval_supervisor_opinion', label: '上级主管部门意见' },
  { key: 'approval_supervisor_sign', label: '上级主管部门签字' },
  { key: 'approval_supervisor_time', label: '签字时间' },
]

const FIELDS_APPROVAL_FIRE: FieldDef[] = [
  { key: 'approval_fire_leader_opinion', label: '动火审批人意见' },
  { key: 'approval_fire_leader_sign', label: '动火审批人签字' },
  { key: 'approval_fire_leader_time', label: '签字时间' },
]

const FIELDS_SHIFT: FieldDef[] = [
  { key: 'shift_leader_check_result', label: '当班班长验票情况' },
  { key: 'shift_leader_sign', label: '当班班长签字' },
  { key: 'shift_leader_time', label: '签字时间' },
]

const FIELDS_COMPLETION: FieldDef[] = [
  { key: 'completion_acceptance_result', label: '完工验收结果' },
  { key: 'completion_acceptance_sign', label: '验收人签字' },
  { key: 'completion_acceptance_time', label: '验收时间' },
]

interface FieldDef {
  key: string
  label: string
  multiline?: boolean
}

interface PermitConfig {
  label: string
  // 基础字段（编号/申请/内容/地点/级别/方式/人员/单位/负责人/联系方式）
  basic: FieldDef[]
  // 时间字段
  hasTime?: boolean
  // 气体分析
  hasGasOverview?: boolean
  hasGasDetail?: boolean
  // 关联/交底
  hasRelated?: boolean
  hasDisclosure?: boolean
  // 审批节（按 GB 30871 顺序：负责人→单位→安全→上级→动火）
  approval: ('owner' | 'unit' | 'safety' | 'supervisor' | 'fire')[]
  // 动火前当班验票
  hasShift?: boolean
  // 完工验收
  hasCompletion?: boolean
  // 安全措施 checkbox 列表
  hasSafetyChecks?: boolean
}

// 8 类票的字段配置（按 GB 30871-2022）
// 注：气体分析是「动火 / 受限空间 / 临时用电」3 类必须
const PERMIT_CONFIGS: Record<string, PermitConfig> = {
  hot_work: {
    label: '动火作业',
    basic: COMMON_BASIC,
    hasTime: true,
    hasGasOverview: true,
    hasGasDetail: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety', 'supervisor', 'fire'],
    hasShift: true,
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  confined_space: {
    label: '受限空间',
    basic: COMMON_BASIC,
    hasTime: true,
    hasGasOverview: true,
    hasGasDetail: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety', 'supervisor'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  blind_plate: {
    label: '盲板抽堵',
    basic: COMMON_BASIC,
    hasTime: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  height: {
    label: '高处作业',
    basic: COMMON_BASIC,
    hasTime: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  lifting: {
    label: '吊装作业',
    basic: COMMON_BASIC,
    hasTime: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety', 'supervisor'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  temp_electric: {
    label: '临时用电',
    basic: COMMON_BASIC,
    hasTime: true,
    // 临时用电作业在有可燃气体环境也需要气体分析
    hasGasOverview: true,
    hasGasDetail: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  excavation: {
    label: '动土作业',
    basic: COMMON_BASIC,
    hasTime: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety', 'supervisor'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
  road_breaking: {
    label: '断路作业',
    basic: COMMON_BASIC,
    hasTime: true,
    hasRelated: true,
    hasDisclosure: true,
    approval: ['owner', 'unit', 'safety'],
    hasCompletion: true,
    hasSafetyChecks: true,
  },
}

const APPROVAL_SECTIONS: Record<string, { id: string; title: string; fields: FieldDef[] }> = {
  owner: { id: 'sec-approval-owner', title: '审批 - 作业负责人', fields: FIELDS_APPROVAL_OWNER },
  unit: { id: 'sec-approval-unit', title: '审批 - 所在单位', fields: FIELDS_APPROVAL_UNIT },
  safety: { id: 'sec-approval-safety', title: '审批 - 安全管理部门', fields: FIELDS_APPROVAL_SAFETY },
  supervisor: { id: 'sec-approval-supervisor', title: '审批 - 上级主管部门', fields: FIELDS_APPROVAL_SUPERVISOR },
  fire: { id: 'sec-approval-fire', title: '审批 - 动火审批人', fields: FIELDS_APPROVAL_FIRE },
}

// ──────────────── Component ────────────────

export default function TicketReview() {
  const classes = useStyles()

  // 票种列表（从后端拉取）
  const [permitTypeList, setPermitTypeList] = useState<{ key: string; label: string }[]>([])
  const [permitType, setPermitType] = useState('hot_work')
  const [pendingPermitType, setPendingPermitType] = useState('hot_work')

  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extracted, setExtracted] = useState<PermitUploadResponse | null>(null)
  const [permit, setPermit] = useState<Record<string, any>>({})
  const [gasAnalyses, setGasAnalyses] = useState<HotWorkGasAnalysis[]>([])
  const [safetyChecks, setSafetyChecks] = useState<ExtractedSafetyCheck[]>([])

  const [permits, setPermits] = useState<HotWorkPermit[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<HotWorkPermit | null>(null)
  const [saving, setSaving] = useState(false)

  const [reviewing, setReviewing] = useState(false)
  const [reviewResults, setReviewResults] = useState<ComplianceReviewItem[]>([])
  const [reviewFilter, setReviewFilter] = useState<string | null>(null)
  const reviewPanelRef = useRef<HTMLDivElement>(null)
  const [highlightSection, setHighlightSection] = useState<string | null>(null)
  const [draftSaved, setDraftSaved] = useState(false)
  const [extractedPermitType, setExtractedPermitType] = useState('hot_work')
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [drafts, setDrafts] = useState<{ permit_type: string; permit: Record<string, any>; gas_analyses: HotWorkGasAnalysis[]; safety_checks: ExtractedSafetyCheck[] }[]>([])
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const formRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 票种对应的 section 顺序表
  const cfg: PermitConfig = PERMIT_CONFIGS[extractedPermitType] || PERMIT_CONFIGS.hot_work
  const permitLabel = cfg.label

  // 初始化：拉取票种列表
  useEffect(() => {
    getPermitTypes()
      .then(list => {
        setPermitTypeList(list)
        // 默认选第一个
        if (list.length > 0) setPermitType(list[0].key)
      })
      .catch(() => {
        // 后端失败时使用本地配置作为 fallback
        setPermitTypeList(
          Object.entries(PERMIT_CONFIGS).map(([k, v]) => ({ key: k, label: v.label })),
        )
      })
  }, [])

  // 刷新列表
  const refreshList = useCallback(async (type: string) => {
    setLoadingList(true)
    try {
      setPermits(await listPermits(type))
    } catch {
      setPermits([])
    } finally {
      setLoadingList(false)
    }
  }, [])

  const loadDraftsFromStorage = () => {
    try {
      const raw = localStorage.getItem('ticket_drafts')
      if (raw) setDrafts(JSON.parse(raw))
    } catch { /* ignore */ }
  }

  useEffect(() => {
    refreshList(permitType)
    loadDraftsFromStorage()
  }, [permitType, refreshList])

  // 切换票种时清空已加载的作业票
  useEffect(() => {
    setExtracted(null)
    setPermit({})
    setGasAnalyses([])
    setSafetyChecks([])
    setReviewResults([])
  }, [permitType])

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const file = files[0]
    const ALLOWED = ['.pdf', '.jpg', '.jpeg', '.png']
    const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
    if (!ALLOWED.includes(fileExt)) {
      setExtractError('仅支持 PDF、JPG、PNG 文件')
      return
    }
    setExtractError(null)
    setExtracting(true)
    setExtracted(null)
    try {
      const result = await uploadAndExtract(file, permitType)
      setExtracted(result)
      setPermit(result.permit || {})
      setGasAnalyses(result.gas_analyses || [])
      setSafetyChecks(result.safety_checks || [])
      setReviewResults([])
      setExtractedPermitType(result.permit_type || permitType)
    } catch (e: any) {
      setExtractError(e.message || '解析失败')
    } finally {
      setExtracting(false)
    }
  }, [permitType])

  const handleLoadDraft = useCallback(async (p: HotWorkPermit) => {
    if (!p.id) return
    try {
      const detail = await getPermit(p.id, permitType)
      setExtracted({ permit: detail.permit, gas_analyses: detail.gas_analyses, safety_checks: [], raw_md: '' } as PermitUploadResponse)
      setPermit(detail.permit)
      setGasAnalyses(detail.gas_analyses)
      const dbSafety: any[] = (detail as any).safety_checks ?? []
      setSafetyChecks(dbSafety.map((s: any) => ({
        description: s.description || '',
        is_confirmed: s.is_confirmed || false,
        confirmed_by: s.confirmed_by || undefined,
      })))
      setReviewResults([])
      setExtractError(null)
    } catch (e: any) {
      setExtractError(e.message || '加载失败')
    }
  }, [permitType])

  const updatePermitField = useCallback((key: string, value: string) => {
    setPermit(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateGasField = useCallback(
    (index: number, key: keyof HotWorkGasAnalysis, value: string) => {
      setGasAnalyses(prev => {
        const next = [...prev]
        next[index] = { ...next[index], [key]: value } as HotWorkGasAnalysis
        return next
      })
    },
    [],
  )

  const toggleSafetyCheck = useCallback((index: number) => {
    setSafetyChecks(prev => {
      const next = [...prev]
      next[index] = { ...next[index], is_confirmed: !next[index].is_confirmed }
      return next
    })
  }, [])

  const updateSafetyCheckDesc = useCallback((index: number, description: string) => {
    setSafetyChecks(prev => {
      const next = [...prev]
      next[index] = { ...next[index], description }
      return next
    })
  }, [])

  const updateSafetyCheckConfirmedBy = useCallback((index: number, confirmed_by: string) => {
    setSafetyChecks(prev => {
      const next = [...prev]
      next[index] = { ...next[index], confirmed_by }
      return next
    })
  }, [])

  const doSave = useCallback(async () => {
    setSaving(true)
    try {
      // 客户环境不存库：仅弹一个提示，但 API 仍调用以保持前端逻辑一致
      // 实际后端 DB_DISABLED=True 时不会写库
      const permitWithStatus = { ...permit, status: 'CONFIRMED' }
      await savePermit({
        permit_type: extractedPermitType,
        permit: permitWithStatus,
        gas_analyses: gasAnalyses,
        safety_checks: safetyChecks,
      })
      setExtracted(null)
      setPermit({})
      setGasAnalyses([])
      setSafetyChecks([])
      setReviewResults([])
      localStorage.removeItem('ticket_draft')
      const rawDrafts = localStorage.getItem('ticket_drafts')
      if (rawDrafts) {
        let allDrafts = JSON.parse(rawDrafts)
        allDrafts = allDrafts.filter((d: any) => d.permit.permit_code !== permit.permit_code)
        localStorage.setItem('ticket_drafts', JSON.stringify(allDrafts))
        setDrafts(allDrafts)
      }
      refreshList(permitType)
    } catch (e: any) {
      setExtractError(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }, [permit, gasAnalyses, safetyChecks, refreshList, permitType, extractedPermitType])

  const handleSaveDraft = useCallback(() => {
    if (!permit.permit_code) return
    const draft = { permit_type: permitType, permit, gas_analyses: gasAnalyses, safety_checks: safetyChecks }
    const raw = localStorage.getItem('ticket_drafts')
    let all: typeof drafts = raw ? JSON.parse(raw) : []
    const idx = all.findIndex(d => d.permit.permit_code === permit.permit_code)
    if (idx >= 0) {
      all[idx] = draft
    } else {
      all.unshift(draft)
    }
    localStorage.setItem('ticket_drafts', JSON.stringify(all))
    setDrafts(all)
    setDraftSaved(true)
    setTimeout(() => setDraftSaved(false), 2000)
  }, [permit, gasAnalyses, safetyChecks, permitType])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget?.id) return
    try {
      await deletePermit(deleteTarget.id, permitType)
      setDeleteTarget(null)
      refreshList(permitType)
    } catch {
      setDeleteTarget(null)
    }
  }, [deleteTarget, refreshList, permitType])

  const handleCancel = useCallback(() => {
    setExtracted(null)
    setPermit({})
    setGasAnalyses([])
    setSafetyChecks([])
    setReviewResults([])
    setExtractError(null)
    localStorage.removeItem('ticket_draft')
  }, [])

  const handleLoadLocalDraft = useCallback((draft: typeof drafts[0]) => {
    setExtracted({
      permit: draft.permit,
      gas_analyses: draft.gas_analyses || [],
      safety_checks: draft.safety_checks || [],
      raw_md: '',
    } as PermitUploadResponse)
    setPermit(draft.permit)
    setGasAnalyses(draft.gas_analyses || [])
    setSafetyChecks(draft.safety_checks || [])
    setReviewResults([])
    setExtractedPermitType(draft.permit_type)
    setPermitType(draft.permit_type)
    setExtractError(null)
  }, [])

  const handleDeleteDraft = useCallback((permitCode: string) => {
    const raw = localStorage.getItem('ticket_drafts')
    let all: typeof drafts = raw ? JSON.parse(raw) : []
    all = all.filter(d => d.permit.permit_code !== permitCode)
    localStorage.setItem('ticket_drafts', JSON.stringify(all))
    setDrafts(all)
  }, [drafts])

  const handleComplianceReview = useCallback(async () => {
    setReviewing(true)
    setReviewResults([])
    try {
      const results = await complianceReview({
        permit_type: extractedPermitType,
        data: { permit, gas_analyses: gasAnalyses, safety_checks: safetyChecks },
      })
      setReviewResults(results)
      setReviewFilter(null)
    } catch (e: any) {
      setExtractError(e.message || '审查失败')
    } finally {
      setReviewing(false)
    }
  }, [permit, gasAnalyses, safetyChecks, extractedPermitType])

  // Map field_key to section ID
  const fieldSectionMap: Record<string, string> = {}
  fieldSectionMap[cfg.basic[0]?.key || 'permit_code'] = 'sec-basic'
  for (const k of cfg.basic.map(f => f.key)) fieldSectionMap[k] = 'sec-basic'
  if (cfg.hasTime) fieldSectionMap['start_time'] = 'sec-time'
  if (cfg.hasGasOverview) {
    for (const f of FIELDS_GAS_OVERVIEW) fieldSectionMap[f.key] = 'sec-gas'
    fieldSectionMap['gas_analyses'] = 'sec-gas-detail'
  }
  if (cfg.hasRelated) for (const f of FIELDS_RELATED) fieldSectionMap[f.key] = 'sec-related'
  if (cfg.hasDisclosure) for (const f of FIELDS_DISCLOSURE) fieldSectionMap[f.key] = 'sec-disclosure'
  for (const k of cfg.approval) {
    const sec = APPROVAL_SECTIONS[k]
    for (const f of sec.fields) fieldSectionMap[f.key] = sec.id
  }
  if (cfg.hasShift) for (const f of FIELDS_SHIFT) fieldSectionMap[f.key] = 'sec-shift'
  if (cfg.hasCompletion) for (const f of FIELDS_COMPLETION) fieldSectionMap[f.key] = 'sec-completion'
  if (cfg.hasSafetyChecks) fieldSectionMap['safety_checks'] = 'sec-safety'

  const handleIssueClick = useCallback((fieldKey: string) => {
    const sectionId = fieldSectionMap[fieldKey]
    if (!sectionId) return
    const el = document.getElementById(sectionId)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlightSection(sectionId)
      if (highlightTimer.current) clearTimeout(highlightTimer.current)
      highlightTimer.current = setTimeout(() => setHighlightSection(null), 2000)
    }
  }, [fieldSectionMap])

  const renderFields = (fields: FieldDef[]) =>
    fields.map(f => (
      <div key={f.key} className={classes.fieldItem} id={`field-${f.key}`}>
        <Label className={classes.fieldLabel}>{f.label}</Label>
        {f.multiline ? (
          <Textarea
            size="small"
            value={(permit[f.key] as string) ?? ''}
            onChange={(_, d) => updatePermitField(f.key, d.value)}
            resize="vertical"
          />
        ) : (
          <Input
            size="small"
            value={(permit[f.key] as string) ?? ''}
            onChange={(_, d) => updatePermitField(f.key, d.value)}
          />
        )}
      </div>
    ))

  const renderSection = (id: string, title: string, fields: FieldDef[]) => (
    <div
      id={id}
      className={`${classes.formSection} ${highlightSection === id ? classes.formSectionHighlight : ''}`}
    >
      <Text className={classes.sectionTitle}>{title}</Text>
      <div className={classes.fieldGrid}>{renderFields(fields)}</div>
    </div>
  )

  const hasReview = reviewResults.length > 0
  const reviewSummary = reviewResults.reduce(
    (acc, r) => { acc[r.status] = (acc[r.status] || 0) + 1; return acc },
    {} as Record<string, number>,
  )
  const sortedResults = reviewFilter
    ? [...reviewResults].sort((a, b) => (a.status === reviewFilter ? -1 : b.status === reviewFilter ? 1 : 0))
    : reviewResults

  useEffect(() => {
    if (reviewFilter && reviewPanelRef.current) {
      reviewPanelRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [reviewFilter])

  // 票种切换器（顶部下拉）
  const permitTypeSelector = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <Text weight="semibold">作业票类型：</Text>
      <Dropdown
        value={PERMIT_CONFIGS[permitType]?.label || permitType}
        selectedOptions={[permitType]}
        onOptionSelect={(_, d) => {
          const v = d.optionValue || 'hot_work'
          setPermitType(v)
          setPendingPermitType(v)
        }}
        style={{ minWidth: 180 }}
      >
        {permitTypeList.map(t => (
          <Option key={t.key} value={t.key}>{t.label}</Option>
        ))}
      </Dropdown>
    </div>
  )

  return (
    <div className={classes.container}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <Text className={classes.title}>作业票智能审查（GB 30871-2022）</Text>
        {!extracted && permitTypeSelector}
      </div>

      {extractError && (
        <MessageBar intent="error">
          <MessageBarBody>{extractError}</MessageBarBody>
        </MessageBar>
      )}

      {!extracted && (
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            style={{ display: 'none' }}
            onChange={e => {
              handleFileSelect(e.target.files)
              setUploadDialogOpen(false)
            }}
          />
          <div className={classes.uploadZone} onClick={() => setUploadDialogOpen(true)}>
            {extracting ? (
              <>
                <ProgressBar />
                <Text className={classes.uploadText}>正在解析文档，请稍候...</Text>
              </>
            ) : (
              <>
                <div className={classes.uploadIcon}>
                  <ArrowUploadRegular />
                </div>
                <Text className={classes.uploadText}>
                  点击上传【{PERMIT_CONFIGS[permitType]?.label || permitType}】作业票 PDF / 图片
                </Text>
              </>
            )}
          </div>
          <Dialog open={uploadDialogOpen} onOpenChange={(_, d) => !d.type && setUploadDialogOpen(false)}>
            <DialogSurface>
              <DialogBody>
                <DialogTitle>选择作业票类型</DialogTitle>
                <DialogContent>
                  <Dropdown
                    value={PERMIT_CONFIGS[pendingPermitType]?.label || pendingPermitType}
                    selectedOptions={[pendingPermitType]}
                    onOptionSelect={(_, d) => setPendingPermitType(d.optionValue || 'hot_work')}
                    style={{ minWidth: 220 }}
                  >
                    {permitTypeList.map(t => (
                      <Option key={t.key} value={t.key}>{t.label}</Option>
                    ))}
                  </Dropdown>
                </DialogContent>
                <DialogActions>
                  <Button appearance="subtle" onClick={() => setUploadDialogOpen(false)}>取消</Button>
                  <Button appearance="primary" onClick={() => {
                    setPermitType(pendingPermitType)
                    setUploadDialogOpen(false)
                    fileInputRef.current?.click()
                  }}>
                    选择文件
                  </Button>
                </DialogActions>
              </DialogBody>
            </DialogSurface>
          </Dialog>
        </>
      )}

      {extracted && (
        <div className={`${classes.mainLayout} ${hasReview ? classes.mainLayoutWithReview : ''}`}>
          <div className={classes.formSide} ref={formRef}>
            {/* 顶部小条：当前票种 + 切换 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', background: tokens.colorBrandBackground2, borderRadius: '8px' }}>
              <Text weight="semibold">当前作业票：{permitLabel}</Text>
              <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>编号：{permit.permit_code || '（未填写）'}</Text>
              <div style={{ flex: 1 }} />
              <Dropdown
                size="small"
                value={PERMIT_CONFIGS[extractedPermitType]?.label || extractedPermitType}
                selectedOptions={[extractedPermitType]}
                onOptionSelect={(_, d) => {
                  const v = d.optionValue || 'hot_work'
                  setExtractedPermitType(v)
                  setPermitType(v)
                }}
                style={{ minWidth: 160 }}
              >
                {permitTypeList.map(t => (
                  <Option key={t.key} value={t.key}>{t.label}</Option>
                ))}
              </Dropdown>
            </div>

            {renderSection('sec-basic', '一、基础信息', cfg.basic)}
            {cfg.hasTime && renderSection('sec-time', '二、作业时间', FIELDS_TIME)}

            {cfg.hasGasOverview && renderSection('sec-gas', '三、气体分析概览', FIELDS_GAS_OVERVIEW)}

            {cfg.hasGasDetail && gasAnalyses.length > 0 && (
              <div
                id="sec-gas-detail"
                className={`${classes.formSection} ${highlightSection === 'sec-gas-detail' ? classes.formSectionHighlight : ''}`}
              >
                <Text className={classes.sectionTitle}>气体分析明细</Text>
                <Table size="small">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>轮次</TableHeaderCell>
                      <TableHeaderCell>取样时间</TableHeaderCell>
                      <TableHeaderCell>代表性气体</TableHeaderCell>
                      <TableHeaderCell>分析结果</TableHeaderCell>
                      <TableHeaderCell>分析人</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {gasAnalyses.map((g, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <Input size="small" value={g.analysis_round?.toString() ?? ''} onChange={(_, d) => updateGasField(i, 'analysis_round', d.value)} style={{ width: 60 }} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={g.sample_time ?? ''} onChange={(_, d) => updateGasField(i, 'sample_time', d.value)} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={g.representative_gas ?? ''} onChange={(_, d) => updateGasField(i, 'representative_gas', d.value)} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={g.analysis_result ?? ''} onChange={(_, d) => updateGasField(i, 'analysis_result', d.value)} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={g.analyst_name ?? ''} onChange={(_, d) => updateGasField(i, 'analyst_name', d.value)} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {cfg.hasSafetyChecks && safetyChecks.length > 0 && (
              <div
                id="sec-safety"
                className={`${classes.formSection} ${highlightSection === 'sec-safety' ? classes.formSectionHighlight : ''}`}
              >
                <Text className={classes.sectionTitle}>安全措施确认</Text>
                <Table size="small">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell style={{ minWidth: 300 }}>措施描述</TableHeaderCell>
                      <TableHeaderCell>是否涉及</TableHeaderCell>
                      <TableHeaderCell>确认人</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {safetyChecks.map((sc, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <Input size="small" value={sc.description} onChange={(_, d) => updateSafetyCheckDesc(i, d.value)} />
                        </TableCell>
                        <TableCell>
                          <Checkbox checked={sc.is_confirmed} onChange={() => toggleSafetyCheck(i)} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={sc.confirmed_by ?? ''} onChange={(_, d) => updateSafetyCheckConfirmedBy(i, d.value)} placeholder="确认人/执行人" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {cfg.hasRelated && renderSection('sec-related', '关联信息与风险辨识', FIELDS_RELATED)}
            {cfg.hasDisclosure && renderSection('sec-disclosure', '安全交底', FIELDS_DISCLOSURE)}

            {/* 审批节：按 GB 30871 顺序 */}
            {cfg.approval.map((k, i) => {
              const sec = APPROVAL_SECTIONS[k]
              return renderSection(sec.id, `审批 ${romanize(i + 1)} - ${sec.title.replace('审批 - ', '')}`, sec.fields)
            })}

            {cfg.hasShift && renderSection('sec-shift', '动火前当班班长验票', FIELDS_SHIFT)}
            {cfg.hasCompletion && renderSection('sec-completion', '完工验收', FIELDS_COMPLETION)}

            <div className={classes.actions}>
              <Button appearance="subtle" icon={<DismissRegular />} onClick={handleCancel}>
                取消
              </Button>
              <Button appearance="subtle" icon={draftSaved ? <CheckmarkRegular /> : <ArrowRedoRegular />} onClick={handleSaveDraft} disabled={saving}>
                {draftSaved ? '已暂存 ✓' : '暂存'}
              </Button>
              <Button appearance="secondary" icon={<ShieldCheckmarkRegular />} onClick={handleComplianceReview} disabled={reviewing}>
                {reviewing ? '审查中...' : '合规性审查'}
              </Button>
              <Button appearance="primary" icon={<SaveRegular />} onClick={doSave} disabled={saving}>
                {saving ? '保存中...' : '确认'}
              </Button>
            </div>
          </div>

          {hasReview && (
            <div className={classes.reviewPanel} ref={reviewPanelRef}>
              <Text className={classes.reviewHeader}>合规性审查结果</Text>
              <div className={classes.reviewSummary}>
                {reviewSummary.pass != null && (
                  <Badge appearance={reviewFilter === 'pass' ? 'filled' : 'ghost'} color="success" size="large" style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'pass' ? 0.5 : 1 }} onClick={() => setReviewFilter(reviewFilter === 'pass' ? null : 'pass')}>合规 {reviewSummary.pass}</Badge>
                )}
                {reviewSummary.warning != null && (
                  <Badge appearance={reviewFilter === 'warning' ? 'filled' : 'ghost'} color="warning" size="large" style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'warning' ? 0.5 : 1 }} onClick={() => setReviewFilter(reviewFilter === 'warning' ? null : 'warning')}>警告 {reviewSummary.warning}</Badge>
                )}
                {reviewSummary.fail != null && (
                  <Badge appearance={reviewFilter === 'fail' ? 'filled' : 'ghost'} color="danger" size="large" style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'fail' ? 0.5 : 1 }} onClick={() => setReviewFilter(reviewFilter === 'fail' ? null : 'fail')}>不合规 {reviewSummary.fail}</Badge>
                )}
              </div>
              <Divider />
              {sortedResults.map((r, i) => (
                <div key={i} className={classes.reviewCategory}>
                  <div className={classes.categoryHeader}>
                    <span className={`${classes.statusBadge} ${r.status === 'pass' ? classes.statusPass : r.status === 'warning' ? classes.statusWarn : classes.statusFail}`}>
                      {r.status === 'pass' ? '合规' : r.status === 'warning' ? '警告' : '不合规'}
                    </span>
                    <Text weight="semibold" size={200}>{r.category}</Text>
                  </div>
                  {r.issues.length === 0 && (
                    <Text size={200} style={{ color: tokens.colorNeutralForeground4 }}>未发现问题</Text>
                  )}
                  {r.issues.map((issue, j) => (
                    <div key={j} className={classes.issueItem} onClick={() => handleIssueClick(issue.field_key)}>
                      <div className={classes.issueText}>{issue.text}</div>
                      {issue.suggestion && (
                        <div className={classes.issueSuggestion}>建议：{issue.suggestion}</div>
                      )}
                      <div className={classes.issueFieldTag}>{issue.field_key}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <Divider />
      <Text className={classes.title} style={{ fontSize: '16px' }}>
        暂存草稿（仅本浏览器）
      </Text>

      {loadingList ? (
        <ProgressBar />
      ) : drafts.length === 0 ? (
        <div className={classes.empty}>
          <DatabaseRegular className={classes.emptyIcon} />
          <Text>暂无暂存草稿</Text>
        </div>
      ) : (
        <div className={classes.tableWrap}>
          <Table size="small">
            <TableHeader>
              <TableRow>
                <TableHeaderCell>编号</TableHeaderCell>
                <TableHeaderCell>类型</TableHeaderCell>
                <TableHeaderCell>作业内容</TableHeaderCell>
                <TableHeaderCell>级别</TableHeaderCell>
                <TableHeaderCell>作业地点</TableHeaderCell>
                <TableHeaderCell>操作</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {drafts.map((d, i) => (
                <TableRow key={`draft-${i}`} className={classes.draftRow} onClick={() => handleLoadLocalDraft(d)}>
                  <TableCell>{d.permit.permit_code || '-'}</TableCell>
                  <TableCell>
                    <Badge appearance="filled" color="informative">{PERMIT_CONFIGS[d.permit_type]?.label || d.permit_type}</Badge>
                  </TableCell>
                  <TableCell>{(d.permit.work_content || '').slice(0, 40)}</TableCell>
                  <TableCell>
                    <Badge appearance="filled" color="informative">{d.permit.work_level || '-'}</Badge>
                  </TableCell>
                  <TableCell>{(d.permit.work_location || '').slice(0, 30)}</TableCell>
                  <TableCell>
                    <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={(e) => { e.stopPropagation(); handleDeleteDraft(d.permit.permit_code) }} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(_, d) => !d.open && setDeleteTarget(null)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>确认删除</DialogTitle>
            <DialogContent>
              确定要删除作业票 <strong>{deleteTarget?.permit_code}</strong> 吗？
            </DialogContent>
            <DialogActions>
              <Button appearance="subtle" onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button appearance="primary" onClick={handleDelete}>删除</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  )
}

// 罗马数字 1-7
function romanize(n: number): string {
  return ['', '一', '二', '三', '四', '五', '六', '七'][n] || String(n)
}

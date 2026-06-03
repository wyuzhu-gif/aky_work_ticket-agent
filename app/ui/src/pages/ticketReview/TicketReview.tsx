/**
 * 作业票数据库页面。
 *
 * 功能：PDF 上传 → MinerU + LLM 提取 → 可编辑表单 + 合规审查 → 暂存/入库。
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
} from '../../services/permitsApi'

// ──────────────── Styles ────────────────

const useStyles = makeStyles({
  container: { display: 'flex', flexDirection: 'column', gap: '24px' },
  title: { fontSize: '20px', fontWeight: 700, color: tokens.colorBrandForeground1 },

  // Two-column layout when review results are present
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

  // Form side
  formSide: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
    minWidth: 0,
  },

  // Review panel (right side)
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
  reviewSummary: {
    display: 'flex',
    gap: '12px',
    marginBottom: '8px',
  },
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

  // Form styles
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

// ──────────────── Field definitions ────────────────

interface FieldDef {
  key: keyof HotWorkPermit
  label: string
  multiline?: boolean
}

const FIELDS_BASIC: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '动火地点及动火部位' },
  { key: 'work_level', label: '动火作业级别' },
  { key: 'work_method', label: '动火方式' },
  { key: 'fire_worker_info', label: '动火人及证书编号' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
]

const FIELDS_TIME: FieldDef[] = [
  { key: 'start_time', label: '作业开始时间' },
  { key: 'end_time', label: '作业结束时间' },
]

const FIELDS_GAS: FieldDef[] = [
  { key: 'gas_analysis_time', label: '气体取样分析时间' },
  { key: 'gas_analyst_name', label: '分析人' },
  { key: 'gas_analysis_result', label: '分析结果' },
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

// Map field_key to section ID for scrolling
const FIELD_SECTION_MAP: Record<string, string> = {}
const allSections: [string, FieldDef[]][] = [
  ['sec-basic', FIELDS_BASIC],
  ['sec-time', FIELDS_TIME],
  ['sec-gas', FIELDS_GAS],
  ['sec-related', FIELDS_RELATED],
  ['sec-disclosure', FIELDS_DISCLOSURE],
  ['sec-approval-owner', FIELDS_APPROVAL_OWNER],
  ['sec-approval-unit', FIELDS_APPROVAL_UNIT],
  ['sec-approval-safety', FIELDS_APPROVAL_SAFETY],
  ['sec-approval-fire', FIELDS_APPROVAL_FIRE],
  ['sec-shift', FIELDS_SHIFT],
  ['sec-completion', FIELDS_COMPLETION],
]
for (const [secId, fields] of allSections) {
  for (const f of fields) {
    FIELD_SECTION_MAP[f.key] = secId
  }
}
FIELD_SECTION_MAP['gas_analyses'] = 'sec-gas-detail'
FIELD_SECTION_MAP['safety_checks'] = 'sec-safety'

// ──────────────── Component ────────────────

export default function TicketReview() {
  const classes = useStyles()

  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extracted, setExtracted] = useState<PermitUploadResponse | null>(null)
  const [permit, setPermit] = useState<HotWorkPermit>({} as HotWorkPermit)
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
  const [permitType, setPermitType] = useState('hot_work')
  const [extractedPermitType, setExtractedPermitType] = useState('hot_work')
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [pendingPermitType, setPendingPermitType] = useState('hot_work')
  const [drafts, setDrafts] = useState<{ permit: HotWorkPermit; gas_analyses: HotWorkGasAnalysis[]; safety_checks: ExtractedSafetyCheck[] }[]>([])
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const formRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refreshList = useCallback(async () => {
    setLoadingList(true)
    try {
      setPermits(await listPermits(permitType))
    } catch {
      /* ignore */
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
    refreshList()
    loadDraftsFromStorage()
  }, [refreshList])

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
      setPermit(result.permit)
      setGasAnalyses(result.gas_analyses)
      setSafetyChecks(result.safety_checks ?? [])
      setReviewResults([])
      setExtractedPermitType(result.permit_type || permitType)
    } catch (e: any) {
      setExtractError(e.message || '解析失败')
    } finally {
      setExtracting(false)
    }
  }, [])

  // Load a draft permit for re-editing
  const handleLoadDraft = useCallback(async (p: HotWorkPermit) => {
    if (!p.id) return
    try {
      const detail = await getPermit(p.id, permitType)
      setExtracted({ permit: detail.permit, gas_analyses: detail.gas_analyses, safety_checks: [], raw_md: '' } as PermitUploadResponse)
      setPermit(detail.permit)
      setGasAnalyses(detail.gas_analyses)
      // Convert safety_checks from DB format back to ExtractedSafetyCheck
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
  }, [])

  const updatePermitField = useCallback((key: keyof HotWorkPermit, value: string) => {
    setPermit(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateGasField = useCallback(
    (index: number, key: keyof HotWorkGasAnalysis, value: string) => {
      setGasAnalyses(prev => {
        const next = [...prev]
        next[index] = { ...next[index], [key]: value }
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

  const doSave = useCallback(async (status: string) => {
    if (!permit) return
    setSaving(true)
    try {
      const permitWithStatus = { ...permit, status }
      await savePermit({ permit_type: extractedPermitType, permit: permitWithStatus, gas_analyses: gasAnalyses, safety_checks: safetyChecks })
      setExtracted(null)
      setPermit({} as HotWorkPermit)
      setGasAnalyses([])
      setSafetyChecks([])
      setReviewResults([])
      localStorage.removeItem('ticket_draft')
      // Also remove from drafts list
      const rawDrafts = localStorage.getItem('ticket_drafts')
      if (rawDrafts) {
        let allDrafts = JSON.parse(rawDrafts)
        allDrafts = allDrafts.filter((d: any) => d.permit.permit_code !== permit.permit_code)
        localStorage.setItem('ticket_drafts', JSON.stringify(allDrafts))
        setDrafts(allDrafts)
      }
      refreshList()
    } catch (e: any) {
      setExtractError(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }, [permit, gasAnalyses, safetyChecks, refreshList])

  const handleSaveDraft = useCallback(() => {
    if (!permit.permit_code) return
    const draft = { permit, gas_analyses: gasAnalyses, safety_checks: safetyChecks }
    // Load existing drafts, add or update by permit_code
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
  }, [permit, gasAnalyses, safetyChecks])
  const handleSubmit = useCallback(() => doSave('CONFIRMED'), [doSave])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget?.id) return
    try {
      await deletePermit(deleteTarget.id, permitType)
      setDeleteTarget(null)
      refreshList()
    } catch {
      /* ignore */
    }
  }, [deleteTarget, refreshList])

  const handleCancel = useCallback(() => {
    setExtracted(null)
    setPermit({} as HotWorkPermit)
    setGasAnalyses([])
    setSafetyChecks([])
    setReviewResults([])
    setExtractError(null)
    localStorage.removeItem('ticket_draft')
  }, [])

  const handleLoadLocalDraft = useCallback((draft: typeof drafts[0]) => {
    setExtracted({ permit: draft.permit, gas_analyses: draft.gas_analyses || [], safety_checks: draft.safety_checks || [], raw_md: '' } as PermitUploadResponse)
    setPermit(draft.permit)
    setGasAnalyses(draft.gas_analyses || [])
    setSafetyChecks(draft.safety_checks || [])
    setReviewResults([])
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
      const results = await complianceReview({ permit_type: permitType, data: { permit, gas_analyses: gasAnalyses, safety_checks: safetyChecks } })
      setReviewResults(results)
      setReviewFilter(null)
    } catch (e: any) {
      setExtractError(e.message || '审查失败')
    } finally {
      setReviewing(false)
    }
  }, [permit, gasAnalyses, safetyChecks])

  // Click issue to scroll to field
  const handleIssueClick = useCallback((fieldKey: string) => {
    const sectionId = FIELD_SECTION_MAP[fieldKey]
    if (!sectionId) return

    const el = document.getElementById(sectionId)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlightSection(sectionId)
      if (highlightTimer.current) clearTimeout(highlightTimer.current)
      highlightTimer.current = setTimeout(() => setHighlightSection(null), 2000)
    }
  }, [])

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

  // Review summary counts
  const reviewSummary = reviewResults.reduce(
    (acc, r) => {
      acc[r.status] = (acc[r.status] || 0) + 1
      return acc
    },
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

  return (
    <div className={classes.container}>
      <Text className={classes.title}>作业票数据库</Text>

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
                  点击上传作业票 PDF / 图片
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
                    value={pendingPermitType === 'hot_work' ? '动火作业' : pendingPermitType === 'confined_space' ? '受限空间' : '盲板抽堵'}
                    selectedOptions={[pendingPermitType]}
                    onOptionSelect={(_, d) => setPendingPermitType(d.optionValue || 'hot_work')}
                    style={{ minWidth: 220 }}
                  >
                    <Option value="hot_work">动火作业</Option>
                    <Option value="confined_space">受限空间</Option>
                    <Option value="blind_plate">盲板抽堵</Option>
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
          {/* Left: Form */}
          <div className={classes.formSide} ref={formRef}>
            {renderSection('sec-basic', '基础信息', FIELDS_BASIC)}
            {renderSection('sec-time', '作业时间', FIELDS_TIME)}
            {renderSection('sec-gas', '气体分析概览', FIELDS_GAS)}

            {gasAnalyses.length > 0 && (
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

            {safetyChecks.length > 0 && (
              <div
                id="sec-safety"
                className={`${classes.formSection} ${highlightSection === 'sec-safety' ? classes.formSectionHighlight : ''}`}
              >
                <Text className={classes.sectionTitle}>安全措施</Text>
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

            {renderSection('sec-related', '关联信息', FIELDS_RELATED)}
            {renderSection('sec-disclosure', '安全交底', FIELDS_DISCLOSURE)}
            {renderSection('sec-approval-owner', '审批 - 作业负责人', FIELDS_APPROVAL_OWNER)}
            {renderSection('sec-approval-unit', '审批 - 所在单位', FIELDS_APPROVAL_UNIT)}
            {renderSection('sec-approval-safety', '审批 - 安全管理部门', FIELDS_APPROVAL_SAFETY)}
            {renderSection('sec-approval-fire', '审批 - 动火审批人', FIELDS_APPROVAL_FIRE)}
            {renderSection('sec-shift', '动火前当班班长验票', FIELDS_SHIFT)}
            {renderSection('sec-completion', '完工验收', FIELDS_COMPLETION)}

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
              <Button appearance="primary" icon={<SaveRegular />} onClick={handleSubmit} disabled={saving}>
                {saving ? '保存中...' : '确认入库'}
              </Button>
            </div>
          </div>

          {/* Right: Review Panel */}
          {hasReview && (
            <div className={classes.reviewPanel} ref={reviewPanelRef}>
              <Text className={classes.reviewHeader}>合规性审查结果</Text>
              <div className={classes.reviewSummary}>
                {reviewSummary.pass != null && (
                  <Badge
                    appearance={reviewFilter === 'pass' ? 'filled' : 'ghost'}
                    color="success" size="large"
                    style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'pass' ? 0.5 : 1 }}
                    onClick={() => setReviewFilter(reviewFilter === 'pass' ? null : 'pass')}
                  >合规 {reviewSummary.pass}</Badge>
                )}
                {reviewSummary.warning != null && (
                  <Badge
                    appearance={reviewFilter === 'warning' ? 'filled' : 'ghost'}
                    color="warning" size="large"
                    style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'warning' ? 0.5 : 1 }}
                    onClick={() => setReviewFilter(reviewFilter === 'warning' ? null : 'warning')}
                  >警告 {reviewSummary.warning}</Badge>
                )}
                {reviewSummary.fail != null && (
                  <Badge
                    appearance={reviewFilter === 'fail' ? 'filled' : 'ghost'}
                    color="danger" size="large"
                    style={{ cursor: 'pointer', opacity: reviewFilter != null && reviewFilter !== 'fail' ? 0.5 : 1 }}
                    onClick={() => setReviewFilter(reviewFilter === 'fail' ? null : 'fail')}
                  >不合规 {reviewSummary.fail}</Badge>
                )}
              </div>
              <Divider />
              {sortedResults.map((r, i) => (
                <div key={i} className={classes.reviewCategory}>
                  <div className={classes.categoryHeader}>
                    <span className={`${classes.statusBadge} ${
                      r.status === 'pass' ? classes.statusPass :
                      r.status === 'warning' ? classes.statusWarn :
                      classes.statusFail
                    }`}>
                      {r.status === 'pass' ? '合规' : r.status === 'warning' ? '警告' : '不合规'}
                    </span>
                    <Text weight="semibold" size={200}>{r.category}</Text>
                  </div>
                  {r.issues.length === 0 && (
                    <Text size={200} style={{ color: tokens.colorNeutralForeground4 }}>未发现问题</Text>
                  )}
                  {r.issues.map((issue, j) => (
                    <div
                      key={j}
                      className={classes.issueItem}
                      onClick={() => handleIssueClick(issue.field_key)}
                    >
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
        已解析作业票
      </Text>

          {loadingList ? (
            <ProgressBar />
          ) : permits.length === 0 ? (
            <div className={classes.empty}>
              <DatabaseRegular className={classes.emptyIcon} />
              <Text>暂无作业票数据</Text>
            </div>
          ) : (
            <div className={classes.tableWrap}>
              <Table size="small">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>编号</TableHeaderCell>
                    <TableHeaderCell>作业内容</TableHeaderCell>
                    <TableHeaderCell>级别</TableHeaderCell>
                    <TableHeaderCell>作业地点</TableHeaderCell>
                    <TableHeaderCell>状态</TableHeaderCell>
                    <TableHeaderCell>创建时间</TableHeaderCell>
                    <TableHeaderCell>操作</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {drafts.map((d, i) => (
                    <TableRow
                      key={`draft-${i}`}
                      className={classes.draftRow}
                      onClick={() => handleLoadLocalDraft(d)}
                    >
                      <TableCell>{d.permit.permit_code || '-'}</TableCell>
                      <TableCell>{(d.permit.work_content || '').slice(0, 40)}</TableCell>
                      <TableCell>
                        <Badge appearance="filled" color="informative">{d.permit.work_level || '-'}</Badge>
                      </TableCell>
                      <TableCell>{(d.permit.work_location || '').slice(0, 30)}</TableCell>
                      <TableCell>
                        <Badge appearance="filled" color="warning">暂存(本地)</Badge>
                      </TableCell>
                      <TableCell>-</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          appearance="subtle"
                          icon={<DeleteRegular />}
                          onClick={(e) => { e.stopPropagation(); handleDeleteDraft(d.permit.permit_code) }}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                  {permits.map(p => (
                    <TableRow
                      key={p.id}
                      className={classes.draftRow}
                      onClick={() => handleLoadDraft(p)}
                    >
                      <TableCell>{p.permit_code || '-'}</TableCell>
                      <TableCell>{(p.work_content || '').slice(0, 40)}</TableCell>
                      <TableCell>
                        <Badge appearance="filled" color="informative">{p.work_level || '-'}</Badge>
                      </TableCell>
                      <TableCell>{(p.work_location || '').slice(0, 30)}</TableCell>
                      <TableCell>
                        <Badge
                          appearance="filled"
                          color={p.status === 'DRAFT' ? 'warning' : 'success'}
                        >
                          {p.status === 'DRAFT' ? '暂存' : p.status || 'DRAFT'}
                        </Badge>
                      </TableCell>
                      <TableCell>{p.create_time || '-'}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          appearance="subtle"
                          icon={<DeleteRegular />}
                          onClick={(e) => { e.stopPropagation(); setDeleteTarget(p) }}
                        />
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
              确定要删除作业票 <strong>{deleteTarget?.permit_code}</strong> 吗？此操作不可恢复。
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

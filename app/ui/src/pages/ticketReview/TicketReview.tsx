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
  Permit,
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
  issueClause: { fontSize: '11px', color: tokens.colorNeutralForeground3, marginTop: '4px', lineHeight: '16px', fontStyle: 'italic' },
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
  key: string  // 改成 string, 不绑 HotWorkPermit
  label: string
  multiline?: boolean
}

// 5 套基础信息字段 (2026-06-11 加 4 类: confined_space / blind_plate / high_above / lifting)
const FIELDS_BASIC_HOT: FieldDef[] = [
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

const FIELDS_BASIC_CONF: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'space_name', label: '受限空间名称/编号' },
  { key: 'original_medium', label: '受限空间内原有介质名称' },
  { key: 'worker_names', label: '作业人姓名 (多人用逗号分隔)' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
  { key: 'risk_identification', label: '危险因素辨识结果', multiline: true },
]

const FIELDS_BASIC_BP: FieldDef[] = [
  { key: 'ticket_code', label: '编号 (右上角)' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'equipment_name', label: '设备、管道名称' },
  { key: 'blind_material', label: '盲板材质' },
  { key: 'blind_spec', label: '盲板规格' },
  { key: 'blocking_purpose', label: '抽堵盲板目的' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
  { key: 'medium_isolation', label: '系统隔离置换情况' },
  { key: 'risk_identification', label: '危险因素辨识', multiline: true },
]

const FIELDS_BASIC_HA: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'work_level', label: '高处作业级别' },
  { key: 'work_height', label: '作业高度' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
  { key: 'worker_names', label: '作业人员名单' },
  { key: 'fall_protection', label: '防坠落措施' },
  { key: 'risk_identification', label: '风险辨识结果', multiline: true },
]

const FIELDS_BASIC_LIFT: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '作业申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'lifting_location', label: '吊装地点' },
  { key: 'lifting_object', label: '吊装物件名称及重量' },
  { key: 'lifting_tool_name', label: '吊具名称 (如吊车/葫芦)' },
  { key: 'command_personnel', label: '指挥人员' },
  { key: 'lifting_operator', label: '吊装作业人' },
  { key: 'lifting_method', label: '吊装方式' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'work_owner_phone', label: '作业负责人联系方式' },
  { key: 'risk_identification', label: '风险辨识', multiline: true },
]

// 临时用电 13 字段 (2026-06-11 加, 用户给字段定义)
const FIELDS_BASIC_TEMP_POWER: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '申请单位' },
  { key: 'apply_time', label: '申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'power_capacity_limit', label: '电源接入点及许可用电功率' },
  { key: 'working_voltage', label: '作业电压' },
  { key: 'equipment_rated_power', label: '用电设备名称及额定功率' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'electrical_operator', label: '用电人' },
  { key: 'work_person', label: '作业人' },
  { key: 'electrician_cert_number', label: '作业人电工证号' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'supervisor_cert_number', label: '作业负责人电工证号' },
  { key: 'attendant', label: '监护人' },
  { key: 'related_permit_ids', label: '关联的其他特殊作业票证' },
  { key: 'risk_identification', label: '安全风险辨识结果', multiline: true },
]

// 动土作业 15 字段 (2026-06-11 加, 用户给字段定义)
const FIELDS_BASIC_EARTHWORK: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '申请时间' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'attendant', label: '监护人' },
  { key: 'related_permit_ids', label: '关联的其他特殊作业及安全作业票编号' },
  { key: 'work_scope', label: '作业范围、内容、方式', multiline: true },
  { key: 'related_explanation_sign', label: '相关说明签字' },
  { key: 'related_explanation_time', label: '相关签名签字时间' },
  { key: 'risk_identification', label: '安全风险辨识结果', multiline: true },
]

// 断路作业 13 字段 (2026-06-11 加, 用户给字段定义)
const FIELDS_BASIC_ROAD_CLOSURE: FieldDef[] = [
  { key: 'permit_code', label: '编号' },
  { key: 'apply_unit', label: '作业申请单位' },
  { key: 'apply_time', label: '申请时间' },
  { key: 'work_content', label: '作业内容', multiline: true },
  { key: 'work_location', label: '作业地点' },
  { key: 'work_unit', label: '作业单位' },
  { key: 'work_owner_name', label: '作业负责人' },
  { key: 'design_unit', label: '设计相关单位 (部门)' },
  { key: 'cutting_reason', label: '断路原因' },
  { key: 'cutting_description', label: '断路地段意图及相关说明', multiline: true },
  { key: 'related_explanation_sign', label: '相关说明签字' },
  { key: 'related_explanation_time', label: '相关签名签字时间' },
  { key: 'related_permit_ids', label: '关联的其他特殊作业及安全作业票编号' },
  { key: 'risk_identification', label: '安全风险辨识结果', multiline: true },
]

const FIELDS_BASIC_BY_TYPE: Record<string, FieldDef[]> = {
  hot_work: FIELDS_BASIC_HOT,
  confined_space: FIELDS_BASIC_CONF,
  blind_plate: FIELDS_BASIC_BP,
  high_above: FIELDS_BASIC_HA,
  lifting: FIELDS_BASIC_LIFT,
  temp_power: FIELDS_BASIC_TEMP_POWER,
  earthwork: FIELDS_BASIC_EARTHWORK,
  road_closure: FIELDS_BASIC_ROAD_CLOSURE,
}

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

// 4 类共有 (高处/吊装/动土/断路) - 审批部门层
const FIELDS_EXECUTIVE_APPROVAL: FieldDef[] = [
  { key: 'executive_approval_opinion', label: '审批部门意见' },
  { key: 'executive_approval_sign', label: '审批部门签字' },
  { key: 'executive_approval_time', label: '审批部门签字时间' },
]

// 临时用电专用 - 用电单位 (GB 30871 字段名)
const FIELDS_DEPARTMENTAL_APPROVAL: FieldDef[] = [
  { key: 'departmental_approval_opinion', label: '用电单位意见' },
  { key: 'departmental_approval_sign', label: '用电单位签字' },
  { key: 'departmental_approval_time', label: '用电单位签字时间' },
]

// 动土专用 - 多部门会签 (1 字段, 1 张会签表)
const FIELDS_DEPARTMENT_APPROVAL: FieldDef[] = [
  { key: 'approval_department_opinion', label: '水、电、汽、工艺、设备、消防、安全等部门会签意见' },
  { key: 'approval_department_sign', label: '多部门会签签字' },
  { key: 'approval_department_time', label: '多部门会签签字时间' },
]

// 断路专用 - 消防、安全部门
const FIELDS_FIRE_SAFETY_APPROVAL: FieldDef[] = [
  { key: 'approval_fire_safety_opinion', label: '消防、安全部门意见' },
  { key: 'approval_fire_safety_sign', label: '消防、安全部门签字' },
  { key: 'approval_fire_safety_time', label: '消防、安全部门签字时间' },
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

// 5 类各自包含的 sections (2026-06-11 加)
// - hot_work: 全部 (含气体分析 + 动火审批人 + 当班班长验票)
// - confined_space: 含气体分析, 没动火审批人/班长验票
// - blind_plate / high_above / lifting / temp_power / earthwork / road_closure: 没气体, 没动火审批人/班长验票
// - high_above / lifting / earthwork / road_closure: 有 executive_approval (审批部门)
// - temp_power: 有 gas (可燃气体) + departmental_approval (用电单位) + 没 executive_approval
// - earthwork: 有 department_approval (多部门会签) + executive_approval (审批部门)
// - road_closure: 有 fire_safety_approval (消防/安全) + executive_approval (审批部门)
const SECTIONS_INC: Record<string, string[]> = {
  hot_work: ['sec-basic', 'sec-time', 'sec-gas', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-approval-safety', 'sec-approval-fire', 'sec-shift', 'sec-completion'],
  confined_space: ['sec-basic', 'sec-time', 'sec-gas', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-approval-safety', 'sec-completion'],
  blind_plate: ['sec-basic', 'sec-time', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-approval-safety', 'sec-completion'],
  high_above: ['sec-basic', 'sec-time', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-approval-safety', 'sec-executive-approval', 'sec-completion'],
  lifting: ['sec-basic', 'sec-time', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-approval-safety', 'sec-executive-approval', 'sec-completion'],
  temp_power: ['sec-basic', 'sec-time', 'sec-gas', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-departmental-approval', 'sec-approval-safety', 'sec-completion'],
  earthwork: ['sec-basic', 'sec-time', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-department-approval', 'sec-executive-approval', 'sec-completion'],
  road_closure: ['sec-basic', 'sec-time', 'sec-related', 'sec-disclosure', 'sec-approval-owner', 'sec-approval-unit', 'sec-fire-safety-approval', 'sec-executive-approval', 'sec-completion'],
}

// 改成函数, 按 permitType 动态选 I2 字段 + sections (2026-06-11)
function getAllSections(permitType: string): [string, FieldDef[]][] {
  const inc = SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']
  const all: [string, FieldDef[]][] = [
    ['sec-basic', FIELDS_BASIC_BY_TYPE[permitType] || FIELDS_BASIC_HOT],
    ['sec-time', FIELDS_TIME],
    ['sec-gas', FIELDS_GAS],
    ['sec-related', FIELDS_RELATED],
    ['sec-disclosure', FIELDS_DISCLOSURE],
    ['sec-approval-owner', FIELDS_APPROVAL_OWNER],
    ['sec-approval-unit', FIELDS_APPROVAL_UNIT],
    ['sec-approval-safety', FIELDS_APPROVAL_SAFETY],
    ['sec-approval-fire', FIELDS_APPROVAL_FIRE],
    ['sec-departmental-approval', FIELDS_DEPARTMENTAL_APPROVAL],  // 临时用电 - 用电单位
    ['sec-department-approval', FIELDS_DEPARTMENT_APPROVAL],     // 动土 - 多部门会签
    ['sec-fire-safety-approval', FIELDS_FIRE_SAFETY_APPROVAL],   // 断路 - 消防/安全
    ['sec-executive-approval', FIELDS_EXECUTIVE_APPROVAL],       // 4 类 - 审批部门
    ['sec-shift', FIELDS_SHIFT],
    ['sec-completion', FIELDS_COMPLETION],
  ]
  return all.filter(([id]) => inc.includes(id))
}
// 把 for 循环改成按 permitType 计算 (2026-06-11)
// FIELD_SECTION_MAP 包含全部 5 类 (供全局搜索/滚动使用)
for (const [, fields] of getAllSections('hot_work')) {
  for (const f of fields) {
    if (!FIELD_SECTION_MAP[f.key]) FIELD_SECTION_MAP[f.key] = 'sec-basic'
  }
}
for (const [, fields] of getAllSections('confined_space')) {
  for (const f of fields) {
    if (!FIELD_SECTION_MAP[f.key]) FIELD_SECTION_MAP[f.key] = 'sec-basic'
  }
}
for (const [, fields] of getAllSections('blind_plate')) {
  for (const f of fields) {
    if (!FIELD_SECTION_MAP[f.key]) FIELD_SECTION_MAP[f.key] = 'sec-basic'
  }
}
for (const [, fields] of getAllSections('high_above')) {
  for (const f of fields) {
    if (!FIELD_SECTION_MAP[f.key]) FIELD_SECTION_MAP[f.key] = 'sec-basic'
  }
}
for (const [, fields] of getAllSections('lifting')) {
  for (const f of fields) {
    if (!FIELD_SECTION_MAP[f.key]) FIELD_SECTION_MAP[f.key] = 'sec-basic'
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
  const [permit, setPermit] = useState<Permit>({} as Permit)
  const [gasAnalyses, setGasAnalyses] = useState<HotWorkGasAnalysis[]>([])
  const [safetyChecks, setSafetyChecks] = useState<ExtractedSafetyCheck[]>([])

  const [permits, setPermits] = useState<Permit[]>([])
  const [loadingList, setLoadingList] = useState(false)
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
  const [drafts, setDrafts] = useState<{ permit_type: string; permit: Permit; gas_analyses: HotWorkGasAnalysis[]; safety_checks: ExtractedSafetyCheck[] }[]>([])
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const formRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 2026-06-12 改: 不再调后端 listPermits (会 500, MySQL king 库没 8 个 permit 表)
  // 改: 只刷 drafts (从 localStorage 加载)
  const refreshList = useCallback(async () => {
    setLoadingList(true)
    try {
      const raw = localStorage.getItem('ticket_drafts')
      setDrafts(raw ? JSON.parse(raw) : [])
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

  // 2026-06-12 修: deps 加 permitType (闭包 bug, 之前 [] 永远捕获 hot_work 初值)
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
  }, [permitType])

  // Load a draft permit for re-editing
  // 2026-06-12 改: 不再调后端 getPermit (会 500)
  // 改: draft 字[已含完整] permit/gas_analyses/safety_checks, 直接填表单
  // 注: handleLoadDraft 由 handleLoadLocalDraft 代替 (后端 getPermit 不用了)

  const updatePermitField = useCallback((key: string, value: string) => {
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
      setPermit({} as Permit)
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
    // 2026-06-11 改: 不再因 permit_code 空就静默返回
    // 用 timestamp 给没有 permit_code 的临时生成一个 key (用 _draft_ 前缀)
    const draftCode = permit.permit_code || `_draft_${Date.now()}`
    const draftPermit = { ...permit, permit_code: draftCode }
    const draft = { permit_type: extractedPermitType, permit: draftPermit, gas_analyses: gasAnalyses, safety_checks: safetyChecks }
    // Load existing drafts, add or update by permit_code
    const raw = localStorage.getItem('ticket_drafts')
    let all: typeof drafts = raw ? JSON.parse(raw) : []
    const idx = all.findIndex(d => d.permit.permit_code === draftCode)
    if (idx >= 0) {
      all[idx] = draft
    } else {
      all.unshift(draft)
    }
    localStorage.setItem('ticket_drafts', JSON.stringify(all))
    setDrafts(all)
    setDraftSaved(true)
    setTimeout(() => setDraftSaved(false), 2000)
  }, [permit, gasAnalyses, safetyChecks, extractedPermitType])
  const handleSubmit = useCallback(() => doSave('CONFIRMED'), [doSave])

  const handleCancel = useCallback(() => {
    setExtracted(null)
    setPermit({} as Permit)
    setGasAnalyses([])
    setSafetyChecks([])
    setReviewResults([])
    setExtractError(null)
    localStorage.removeItem('ticket_draft')
  }, [])

  const handleLoadLocalDraft = useCallback((draft: typeof drafts[0]) => {
    setExtractedPermitType(draft.permit_type)
    setPermitType(draft.permit_type)  // 修 bug: 渲染用的是 permitType, 不是 extractedPermitType
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
                    value={
                      pendingPermitType === 'hot_work' ? '动火作业' :
                      pendingPermitType === 'confined_space' ? '受限空间' :
                      pendingPermitType === 'blind_plate' ? '盲板抽堵' :
                      pendingPermitType === 'high_above' ? '高处作业' :
                      pendingPermitType === 'lifting' ? '吊装作业' :
                      pendingPermitType === 'temp_power' ? '临时用电' :
                      pendingPermitType === 'earthwork' ? '动土作业' :
                      pendingPermitType === 'road_closure' ? '断路作业' : '动火作业'
                    }
                    selectedOptions={[pendingPermitType]}
                    onOptionSelect={(_, d) => setPendingPermitType(d.optionValue || 'hot_work')}
                    style={{ minWidth: 220 }}
                  >
                    <Option value="hot_work">动火作业</Option>
                    <Option value="confined_space">受限空间</Option>
                    <Option value="blind_plate">盲板抽堵</Option>
                    <Option value="high_above">高处作业</Option>
                    <Option value="lifting">吊装作业</Option>
                    <Option value="temp_power">临时用电</Option>
                    <Option value="earthwork">动土作业</Option>
                    <Option value="road_closure">断路作业</Option>
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
            {renderSection('sec-basic', '基础信息', FIELDS_BASIC_BY_TYPE[permitType] || FIELDS_BASIC_HOT)}
            {renderSection('sec-time', '作业时间', FIELDS_TIME)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-gas') &&
              renderSection('sec-gas', '气体分析概览', FIELDS_GAS)}

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
                <Text className={classes.sectionTitle}>安全措施 ({safetyChecks.length} 条)</Text>
                <Table size="small" style={{ tableLayout: 'fixed', width: '100%' }}>
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell style={{ width: '6%' }}>序号</TableHeaderCell>
                      <TableHeaderCell style={{ width: '64%' }}>措施描述</TableHeaderCell>
                      <TableHeaderCell style={{ width: '12%' }}>是否涉及</TableHeaderCell>
                      <TableHeaderCell style={{ width: '18%' }}>确认人</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {safetyChecks.map((sc, i) => (
                      <TableRow key={i}>
                        <TableCell style={{ textAlign: 'center', color: tokens.colorNeutralForeground3, fontWeight: 600 }}>
                          {i + 1}
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={sc.description} onChange={(_, d) => updateSafetyCheckDesc(i, d.value)} style={{ width: '100%' }} />
                        </TableCell>
                        <TableCell>
                          <Checkbox checked={sc.is_confirmed} onChange={() => toggleSafetyCheck(i)} />
                        </TableCell>
                        <TableCell>
                          <Input size="small" value={sc.confirmed_by ?? ''} onChange={(_, d) => updateSafetyCheckConfirmedBy(i, d.value)} placeholder="确认人" style={{ width: '100%' }} />
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
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-departmental-approval') &&
              renderSection('sec-departmental-approval', '审批 - 用电单位', FIELDS_DEPARTMENTAL_APPROVAL)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-department-approval') &&
              renderSection('sec-department-approval', '审批 - 多部门会签', FIELDS_DEPARTMENT_APPROVAL)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-fire-safety-approval') &&
              renderSection('sec-fire-safety-approval', '审批 - 消防、安全部门', FIELDS_FIRE_SAFETY_APPROVAL)}
            {renderSection('sec-approval-safety', '审批 - 安全管理部门', FIELDS_APPROVAL_SAFETY)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-approval-fire') &&
              renderSection('sec-approval-fire', '审批 - 动火审批人', FIELDS_APPROVAL_FIRE)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-shift') &&
              renderSection('sec-shift', '动火前当班班长验票', FIELDS_SHIFT)}
            {(SECTIONS_INC[permitType] || SECTIONS_INC['hot_work']).includes('sec-executive-approval') &&
              renderSection('sec-executive-approval', '审批 - 审批部门', FIELDS_EXECUTIVE_APPROVAL)}
            {renderSection('sec-completion', '完工验收', FIELDS_COMPLETION)}

            <div className={classes.actions}>
              <Button appearance="subtle" onClick={handleCancel}>
                <DismissRegular style={{ marginRight: 4 }} />
                取消
              </Button>
              <Button appearance="subtle" onClick={handleSaveDraft} disabled={saving}>
                {draftSaved ? <CheckmarkRegular style={{ marginRight: 4 }} /> : <ArrowRedoRegular style={{ marginRight: 4 }} />}
                {draftSaved ? '已暂存 ✓' : '暂存'}
              </Button>
              <Button appearance="secondary" onClick={handleComplianceReview} disabled={reviewing}>
                <ShieldCheckmarkRegular style={{ marginRight: 4 }} />
                {reviewing ? '审查中...' : '合规性审查'}
              </Button>
              <Button appearance="primary" onClick={() => { handleSaveDraft(); setTimeout(() => { setExtracted(null); setPermit({} as Permit); setGasAnalyses([]); setSafetyChecks([]); setReviewResults([]); setExtractError(null); }, 500); }} disabled={saving}>
                <SaveRegular style={{ marginRight: 4 }} />
                暂存并新建
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
                      {issue.clause && (
                        <div className={classes.issueClause}>📖 {issue.clause}</div>
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
        暂存作业票 (本地)
      </Text>

          {loadingList ? (
            <ProgressBar />
          ) : drafts.length === 0 ? (
            <div className={classes.empty}>
              <DatabaseRegular className={classes.emptyIcon} />
              <Text>暂无作业票数据</Text>
            </div>
          ) : (
            <div className={classes.tableWrap}>
              <Table size="small" style={{ tableLayout: 'fixed', width: '100%' }}>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell style={{ width: '15%' }}>编号</TableHeaderCell>
                    <TableHeaderCell style={{ width: '30%' }}>作业内容</TableHeaderCell>
                    <TableHeaderCell style={{ width: '20%' }}>作业地点</TableHeaderCell>
                    <TableHeaderCell style={{ width: '12%' }}>类别</TableHeaderCell>
                    <TableHeaderCell style={{ width: '10%' }}>状态</TableHeaderCell>
                    <TableHeaderCell style={{ width: '8%' }}>创建时间</TableHeaderCell>
                    <TableHeaderCell style={{ width: '5%' }}>操作</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {drafts.map((d, i) => (
                    <TableRow
                      key={`draft-${i}`}
                      className={classes.draftRow}
                      onClick={() => handleLoadLocalDraft(d)}
                    >
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.permit.permit_code || '-'}</TableCell>
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(d.permit.work_content || '').slice(0, 80)}</TableCell>
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(d.permit.work_location || '').slice(0, 50)}</TableCell>
                      <TableCell>
                        <Badge appearance="filled" color="informative">
                          {(d.permit_type || 'hot_work') === 'hot_work' ? '动火作业' :
                           (d.permit_type || 'hot_work') === 'confined_space' ? '受限空间' :
                           (d.permit_type || 'hot_work') === 'blind_plate' ? '盲板抽堵' :
                           (d.permit_type || 'hot_work') === 'high_above' ? '高处作业' :
                           (d.permit_type || 'hot_work') === 'lifting' ? '吊装作业' :
                           (d.permit_type || 'hot_work') === 'temp_power' ? '临时用电' :
                           (d.permit_type || 'hot_work') === 'earthwork' ? '动土作业' :
                           (d.permit_type || 'hot_work') === 'road_closure' ? '断路作业' : '-'}
                        </Badge>
                      </TableCell>
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
                </TableBody>
              </Table>
            </div>
          )}
    </div>
  )
}

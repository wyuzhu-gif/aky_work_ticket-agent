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
  ChevronDownRegular,
  ChevronRightRegular,
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
  hermesReview,
  hermesWarmup,
  hermesStatus,
  saveDraft,
  listDrafts,
  getDraft,
  deleteDraft,
  DraftSummary,
  DraftDetail,
} from '../../services/permitsApi'

//  ──────────────── Styles ────────────────

// 字段名翻译表 (英文 → 中文), 业务用户看不懂英文代码
const FIELD_NAME_CN: Record<string, string> = {
  'permit_code': '作业票编号',
  'work_content': '作业内容',
  'work_location': '作业地点',
  'work_unit': '作业单位',
  'apply_unit': '申请单位',
  'work_level': '作业级别',
  'work_type': '作业类型',
  'plan_start': '计划开始时间',
  'plan_end': '计划结束时间',
  'actual_start': '实际开始时间',
  'complete_time': '完工时间',
  'gas_analysis': '气体分析',
  'gas_analyses': '气体分析',
  'safety_measures': '安全措施',
  'safety_checks': '安全措施',
  'task_manager': '作业负责人',
  'safe_disclose_person': '安全交底人',
  'operator': '作业人员',
  'guardian': '监护人',
  'fire_watcher': '监火人',
  'approver': '审批人',
  'permit_type': '作业票类型',
  'special_task_view': '特殊作业票',
  'top_level': '作业大类',
  'sub_level': '作业小类',
  // 2026-06-22 补: 安全措施 / 气体分析 内部字段
  // 这些是 ExtractedSafetyCheck / HotWorkGasAnalysis 里的 key,
  // LLM 审查时拿 key 当描述, 业务人员看不懂
  'is_confirmed': '是否确认',
  'confirmed_by': '确认人',
  'description': '措施内容',
  'check_item': '检查项',
  'result': '结果',
  'remark': '备注',
  'o2': '氧气浓度',
  'ch4': '甲烷浓度',
  'co': '一氧化碳浓度',
  'h2s': '硫化氢浓度',
  'time': '检测时间',
  'location': '检测位置',
  'temperature': '温度',
  'humidity': '湿度',
  'applicant_name': '申请人',
  'work_start': '开始时间',
  'work_end': '结束时间',
  'fire_watch': '监火人',
}

// 2026-06-22 新增: 把审查文本里嵌入的英文 key 替换成中文
// 优先级: 单词边界匹配, 避免误伤 (is_confirmed= 不会跟 is_confirmed_other 撞)
// 顺序: 长的在前 (confirmed_by 优先于 confirmed)
const FIELD_NAME_REGEX_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bconfirmed_by\b/g, '确认人'],
  [/\bis_confirmed\b/g, '是否确认'],
  [/\bcheck_item\b/g, '检查项'],
  [/\bgas_analyses\b/g, '气体分析'],
  [/\bsafety_checks\b/g, '安全措施'],
  [/\bwork_content\b/g, '作业内容'],
  [/\bwork_location\b/g, '作业地点'],
  [/\bwork_unit\b/g, '作业单位'],
  [/\bapply_unit\b/g, '申请单位'],
  [/\bwork_level\b/g, '作业级别'],
  [/\bwork_type\b/g, '作业类型'],
  [/\bplan_start\b/g, '计划开始时间'],
  [/\bplan_end\b/g, '计划结束时间'],
  [/\bpermit_code\b/g, '作业票编号'],
  [/\bpermit_type\b/g, '作业票类型'],
  [/\bspecial_task_view\b/g, '特殊作业票'],
  [/\btop_level\b/g, '作业大类'],
  [/\bsub_level\b/g, '作业小类'],
  [/\boperator\b/g, '作业人员'],
  [/\bguardian\b/g, '监护人'],
  [/\bfire_watcher\b/g, '监火人'],
  [/\bapprover\b/g, '审批人'],
  [/\btask_manager\b/g, '作业负责人'],
  [/\bsafe_disclose_person\b/g, '安全交底人'],
]

/**
 * 2026-06-22 新增: 把审查文本里嵌入的英文字段名替换成中文
 * 例: "is_confirmed=false 与 confirmed_by=韩志良 矛盾" → "是否确认=false 与 确认人=韩志良 矛盾"
 */
function humanizeReviewText(text: string): string {
  if (!text) return text
  let out = text
  for (const [re, cn] of FIELD_NAME_REGEX_REPLACEMENTS) {
    out = out.replace(re, cn)
  }
  return out
}

/**
 * 2026-06-22 新增: 翻译 field/category key 为中文
 * 例: r.field = "is_confirmed" → "是否确认"
 */
function fieldLabel(key: string | undefined, fallback: string = ''): string {
  if (!key) return fallback
  return FIELD_NAME_CN[key] || key
}

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
      borderTopColor: tokens.colorBrandStroke1,
      borderRightColor: tokens.colorBrandStroke1,
      borderBottomColor: tokens.colorBrandStroke1,
      borderLeftColor: tokens.colorBrandStroke1,
      backgroundColor: tokens.colorBrandBackground2,
    },
  },
  issueText: { fontSize: '13px', color: tokens.colorNeutralForeground1, lineHeight: '20px' },
  issueSuggestion: { fontSize: '12px', color: tokens.colorBrandForeground1, marginTop: '4px', lineHeight: '18px' },
  issueClause: { fontSize: '11px', color: tokens.colorNeutralForeground3, marginTop: '4px', lineHeight: '16px', fontStyle: 'italic' },
  issueClauseContent: { fontSize: '11px', color: tokens.colorNeutralForeground2, marginTop: '2px', lineHeight: '16px', padding: '4px 6px', backgroundColor: tokens.colorNeutralBackground2, borderLeft: `2px solid ${tokens.colorBrandForeground1}`, borderRadius: 2, whiteSpace: 'pre-wrap' as const, fontStyle: 'italic' as const },
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
    borderTop: `2px dashed ${tokens.colorNeutralStroke2}`,
    borderRight: `2px dashed ${tokens.colorNeutralStroke2}`,
    borderBottom: `2px dashed ${tokens.colorNeutralStroke2}`,
    borderLeft: `2px dashed ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    padding: '40px',
    textAlign: 'center',
    cursor: 'pointer',
    transitionProperty: 'border-color, background-color',
    transitionDuration: '200ms',
    '&:hover': {
      borderTopColor: tokens.colorBrandStroke1,
      borderRightColor: tokens.colorBrandStroke1,
      borderBottomColor: tokens.colorBrandStroke1,
      borderLeftColor: tokens.colorBrandStroke1,
      backgroundColor: tokens.colorBrandBackground2,
    },
  },
  uploadIcon: { fontSize: '36px', color: tokens.colorBrandForeground1, marginBottom: '12px' },
  uploadText: { color: tokens.colorNeutralForeground3, fontSize: '14px' },

  formSection: {
    padding: '20px',
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    borderLeft: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    transitionProperty: 'border-color, box-shadow',
    transitionDuration: '300ms',
  },
  formSectionHighlight: {
    borderTopColor: tokens.colorBrandStroke1,
    borderRightColor: tokens.colorBrandStroke1,
    borderBottomColor: tokens.colorBrandStroke1,
    borderLeftColor: tokens.colorBrandStroke1,
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
  const [drafts, setDrafts] = useState<DraftSummary[]>([])
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const formRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 2026-06-22 改: 后端 SQLite (permit_drafts 表) — 跨设备/同事都能看, 不会丢
  // 替代原 localStorage (同浏览器才看得到)
  const refreshList = useCallback(async () => {
    setLoadingList(true)
    try {
      const list = await listDrafts()
      setDrafts(list)
    } catch (e) {
      // 后端拉取失败, 容错: 留空列表, 提示用户
      console.error('listDrafts failed', e)
      setDrafts([])
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
      // 2026-06-22 改: 草稿入库成功, 后端删草稿 (跨设备, 不依赖 localStorage)
      if (permit.permit_code) {
        try {
          await deleteDraft(permit.permit_code)
          setDrafts(prev => prev.filter(d => d.permit_code !== permit.permit_code))
        } catch {
          /* 草稿没找到 / 已删, 忽略 */
        }
      }
      refreshList()
    } catch (e: any) {
      setExtractError(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }, [permit, gasAnalyses, safetyChecks, refreshList])

  // 2026-06-22 改: 调后端 saveDraft (permit_drafts 表, 跨设备持久化)
  // reviewResults 一起存, 已审查的草稿重新加载不丢审查结果
  const handleSaveDraft = useCallback(async () => {
    const draftCode = permit.permit_code || `_draft_${Date.now()}`
    const draftPermit = { ...permit, permit_code: draftCode }
    try {
      const saved = await saveDraft({
        permit_code: draftCode,
        permit_type: extractedPermitType,
        permit: draftPermit,
        gas_analyses: gasAnalyses,
        safety_checks: safetyChecks,
        review_results: reviewResults,
      })
      // 同步本地 state (让列表立刻刷出来, 不依赖 refreshList 二次请求)
      setDrafts(prev => {
        const idx = prev.findIndex(d => d.permit_code === saved.permit_code)
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = saved
          return next
        }
        return [saved, ...prev]
      })
      // 如果原 permit 没有 code, 把当前表单的 permit_code 同步成 draftCode
      // (这样再点暂存会覆盖同一个, 而不会又生成一个新的 _draft_)
      if (!permit.permit_code) {
        setPermit(prev => ({ ...prev, permit_code: draftCode }))
      }
      setDraftSaved(true)
      setTimeout(() => setDraftSaved(false), 2000)
    } catch (e: any) {
      console.error('saveDraft failed', e)
      setExtractError(`暂存失败: ${e?.message || e}`)
    }
  }, [permit, gasAnalyses, safetyChecks, reviewResults, extractedPermitType])
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

  // 2026-06-22 改: 列表项是 DraftSummary (只有 permit_type + permit_code + has_review 等元信息)
  // 实际数据 + 审查结果要再 GET /api/v1/drafts/{code} 拉详情
  const handleLoadLocalDraft = useCallback(async (summary: DraftSummary) => {
    try {
      const detail: DraftDetail = await getDraft(summary.permit_code)
      setExtractedPermitType(detail.permit_type)
      setPermitType(detail.permit_type)  // 修 bug: 渲染用的是 permitType, 不是 extractedPermitType
      setExtracted({
        permit: detail.permit,
        gas_analyses: detail.gas_analyses || [],
        safety_checks: detail.safety_checks || [],
        raw_md: '',
      } as PermitUploadResponse)
      setPermit(detail.permit)
      setGasAnalyses(detail.gas_analyses || [])
      setSafetyChecks(detail.safety_checks || [])
      // 2026-06-22 关键: 恢复 AI 审查结果, 重新加载不丢
      setReviewResults(detail.review_results || [])
      setExtractError(null)
    } catch (e: any) {
      console.error('getDraft failed', e)
      setExtractError(`加载草稿失败: ${e?.message || e}`)
    }
  }, [])

  const handleDeleteDraft = useCallback(async (permitCode: string) => {
    try {
      await deleteDraft(permitCode)
      setDrafts(prev => prev.filter(d => d.permit_code !== permitCode))
    } catch (e: any) {
      console.error('deleteDraft failed', e)
      setExtractError(`删除草稿失败: ${e?.message || e}`)
    }
  }, [])

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

  // Hermes AI 审查 - 调 hermes subprocess + llm-wiki
  const [hermesReviewing, setHermesReviewing] = useState(false)
  const [hermesElapsed, setHermesElapsed] = useState<number | null>(null)
  const handleHermesReview = useCallback(async () => {
    setHermesReviewing(true)
    setHermesElapsed(null)
    setReviewResults([])
    try {
      // 预热 (后台启动 hermes, 让审查时更快)
      hermesWarmup().catch(() => { /* 忽略预热失败, 审查时会再试 */ })
      // 审查
      const resp = await hermesReview({
        permit_type: permitType,
        permit,
        gas_analyses: gasAnalyses,
        safety_checks: safetyChecks,
      })
      setHermesElapsed(resp.elapsed || 0)
      if (resp.ok && resp.results) {
        setReviewResults(resp.results)
        setReviewFilter(null)
      } else {
        setExtractError(`Hermes 审查失败: ${resp.error || '未知错误'}`)
      }
    } catch (e: any) {
      setExtractError(e.message || 'Hermes 审查失败')
    } finally {
      setHermesReviewing(false)
    }
  }, [permit, gasAnalyses, safetyChecks, permitType])

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
              // 关键: 同步复制 FileList (React 可能复用 input 导致 e.target.files 变 null)
              const files = e.target.files ? Array.from(e.target.files) : null
              const fileInput = e.target
              handleFileSelect(files ? (files as any) : null)
              setUploadDialogOpen(false)
              // 重置 input, 让同一文件能再次选
              setTimeout(() => { if (fileInput) fileInput.value = '' }, 0)
            }}
          />
          <div className={classes.uploadZone} onClick={() => setUploadDialogOpen(true)}>
            {extracting ? (
              <>
                <ProgressBar />
                <Text className={classes.uploadText}>正在解析文档，请稍候...</Text>
                <Text className={classes.uploadText} style={{ fontSize: '12px', marginTop: 8, color: tokens.colorNeutralForeground4 }}>
                  通常需要 30-60 秒 (PDF 解析 + LLM 字段提取)
                </Text>
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
                    // 关键: 延迟 100ms click file input, 让 dialog 先完全关闭
                    // 否则浏览器会忽略 file picker (modal 互斥)
                    setTimeout(() => {
                      fileInputRef.current?.click()
                    }, 100)
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
                {draftSaved ? '已保存到本地 ✓' : '保存到本地'}
              </Button>
              <Button
                appearance="secondary"
                onClick={handleHermesReview}
                disabled={hermesReviewing || reviewing}
                title="调 hermes subprocess + llm-wiki 查 GB 30871 等标准, 深度审查 (约 30-60s)"
              >
                <span style={{ marginRight: 4 }}>🤖</span>
                {hermesReviewing ? 'AI 审查中...' : 'AI 合规性审查'}
              </Button>
              <Button
                appearance="primary"
                onClick={async () => {
                  await handleSaveDraft()
                  // 暂存成功后清空表单, 准备新建下一张
                  setExtracted(null)
                  setPermit({} as Permit)
                  setGasAnalyses([])
                  setSafetyChecks([])
                  setReviewResults([])
                  setExtractError(null)
                }}
                disabled={saving}
              >
                <SaveRegular style={{ marginRight: 4 }} />
                保存到本地
              </Button>
            </div>
          </div>

          {/* Right: Review Panel */}
          {hasReview && (
            <div className={classes.reviewPanel} ref={reviewPanelRef}>
              <Text className={classes.reviewHeader}>AI 合规性审查结果</Text>
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
              {sortedResults.map((r, i) => {
                // 兼容两种格式: 旧版 {category, status, issues: [...]} 和新版 {field, severity, issue, clause, suggestion}
                const severity = r.status || r.severity || 'fail'
                return (
                <div key={i} className={classes.reviewCategory}>
                  <div className={classes.categoryHeader}>
                    <span className={`${classes.statusBadge} ${
                      severity === 'pass' ? classes.statusPass :
                      severity === 'warning' ? classes.statusWarn :
                      classes.statusFail
                    }`}>
                      {severity === 'pass' ? '合规' : severity === 'warning' ? '警告' : '不合规'}
                    </span>
                    <Text weight="semibold" size={200}>{fieldLabel(r.category || r.field, `项目 ${i + 1}`)}</Text>
                  </div>
                  {/* 兼容两种格式: 旧版 {issues: [...]} 和新版 {field, issue, clause, suggestion} */}
                  {(() => {
                    const issues = r.issues || [r]
                    if (!issues || issues.length === 0) {
                      return <Text size={200} style={{ color: tokens.colorNeutralForeground4 }}>未发现问题</Text>
                    }
                    return issues.map((issue, j) => {
                      // 新格式: {field, issue, clause, suggestion, clause_content}
                      // 旧格式: {text, field_key, suggestion, clause}
                      const text = humanizeReviewText(issue.text || issue.issue || '')
                      const fieldKey = issue.field_key || issue.field || ''
                      const clause = issue.clause || ''
                      const clauseContent = humanizeReviewText(issue.clause_content || '')
                      const suggestion = humanizeReviewText(issue.suggestion || '')
                      return (
                        <div
                          key={j}
                          className={classes.issueItem}
                          onClick={() => handleIssueClick(fieldKey)}
                        >
                          <div className={classes.issueText}>{text}</div>
                          {suggestion && (
                            <div className={classes.issueSuggestion}>建议：{suggestion}</div>
                          )}
                          {clause && (
                            <div className={classes.issueClause}>📖 {clause}</div>
                          )}
                          {clauseContent && (
                            <ClauseContentFoldable content={clauseContent} />
                          )}
                          {fieldKey && (
                            <div
                              className={classes.issueFieldTag}
                              title={fieldKey}
                            >
                              {FIELD_NAME_CN[fieldKey] || fieldKey}
                            </div>
                          )}
                        </div>
                      )
                    })
                  })()}
                </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <Divider />
      <Text className={classes.title} style={{ fontSize: '16px' }}>
        已保存到本地的作业票
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
                      key={`draft-${d.permit_code}`}
                      className={classes.draftRow}
                      onClick={() => handleLoadLocalDraft(d)}
                    >
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.permit_code || '-'}</TableCell>
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(d.permit_job || '').slice(0, 80)}</TableCell>
                      <TableCell style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{(d.permit_location || '').slice(0, 50)}</TableCell>
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
                        <Badge appearance="filled" color="warning">已保存到本地</Badge>
                      </TableCell>
                      <TableCell>-</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          appearance="subtle"
                          icon={<DeleteRegular />}
                          onClick={(e) => { e.stopPropagation(); handleDeleteDraft(d.permit_code) }}
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

// ──────────────── Clause Content Foldable ────────────────

/** 折叠的条款原文组件 - 默认折叠, 用户点击展开 */
function ClauseContentFoldable({ content }: { content: string }) {
  const classes = useStyles()
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ marginTop: '2px' }}>
      <Button
        size="small"
        appearance="subtle"
        onClick={() => setExpanded(!expanded)}
        icon={expanded ? <ChevronDownRegular /> : <ChevronRightRegular />}
        style={{ fontSize: '11px', height: 22, padding: '0 6px' }}
      >
        {expanded ? '收起条款原文' : '查看条款原文'}
      </Button>
      {expanded && (
        <div className={classes.issueClauseContent}>原文：{content}</div>
      )}
    </div>
  )
}

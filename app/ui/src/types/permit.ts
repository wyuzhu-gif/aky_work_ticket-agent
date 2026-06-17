/**
 * 作业票 TypeScript 类型定义 (2026-06-11 改为通用 Permit).
 *
 * 之前是 HotWorkPermit (硬编码动火字段), 改成通用 Permit
 * (支持 8 类特殊作业: hot_work / confined_space / blind_plate /
 *  high_above / lifting / temp_power / earthwork / road_closure).
 * 各类的字段定义见 TicketReview.tsx 的 FIELDS_BASIC_BY_TYPE.
 */

export type PermitType =
  | 'hot_work'
  | 'confined_space'
  | 'blind_plate'
  | 'high_above'
  | 'lifting'
  | 'temp_power'
  | 'earthwork'
  | 'road_closure'

// 通用 Permit: 任意 string 字段 (含 8 类各自独有的字段)
export interface Permit {
  id?: number
  permit_code: string
  work_id?: string

  // 通用基础信息
  apply_unit?: string
  apply_time?: string
  work_content?: string
  work_location?: string
  work_level?: string
  work_method?: string
  work_unit?: string
  work_owner_name?: string
  work_owner_phone?: string

  // 动火独有
  fire_worker_info?: string

  // 受限空间独有
  space_name?: string
  original_medium?: string
  worker_names?: string

  // 盲板抽堵独有
  ticket_code?: string
  equipment_name?: string
  blind_material?: string
  blind_spec?: string
  blocking_purpose?: string
  medium_isolation?: string

  // 高处作业独有
  work_height?: string
  fall_protection?: string

  // 吊装作业独有
  lifting_location?: string
  lifting_object?: string
  lifting_tool_name?: string
  lifting_method?: string
  lifting_operator?: string
  command_personnel?: string

  // 临时用电独有 (2026-06-11 加, 用户给字段定义)
  power_capacity_limit?: string       // 电源接入点及许可用电功率
  working_voltage?: string             // 作业电压
  equipment_rated_power?: string       // 用电设备名称及额定功率
  electrical_operator?: string        // 用电人
  work_person?: string                 // 作业人
  electrician_cert_number?: string     // 作业人电工证号
  supervisor_cert_number?: string      // 作业负责人电工证号
  departmental_approval_opinion?: string  // 用电单位意见 (GB 30871 字段名)
  departmental_approval_sign?: string     // 用电单位签字
  departmental_approval_time?: string     // 用电单位签字时间

  // 动土作业独有 (2026-06-11 加, 用户给字段定义)
  work_scope?: string                  // 作业范围、内容、方式
  related_explanation_sign?: string    // 相关说明签字
  related_explanation_time?: string    // 相关签名签字时间
  approval_department_opinion?: string // 水、电、汽、工艺、设备、消防、安全等部门会签意见 (1 字段, 1 张会签表)
  approval_department_sign?: string    // 多部门会签签字
  approval_department_time?: string    // 多部门会签签字时间

  // 断路作业独有 (2026-06-11 加, 用户给字段定义)
  design_unit?: string                 // 设计相关单位 (部门)
  cutting_reason?: string              // 断路原因
  cutting_description?: string         // 断路地段意图及相关说明 (不用 lifting_tool_name 复用)
  approval_fire_safety_opinion?: string // 消防、安全部门意见 (GB 30871 字段名)
  approval_fire_safety_sign?: string    // 消防、安全部门签字
  approval_fire_safety_time?: string    // 消防、安全部门签字时间

  // 4 类共有的"审批部门"层 (高处/吊装/动土/断路)
  executive_approval_opinion?: string  // 审批部门意见
  executive_approval_sign?: string     // 审批部门签字
  executive_approval_time?: string     // 审批部门签字时间

  // 气体分析
  gas_analysis_time?: string
  gas_analyst_name?: string
  gas_analysis_result?: string

  // 关联 + 风险
  related_permit_ids?: string
  risk_identification?: string

  // 时间
  start_time?: string
  end_time?: string

  // 安全交底
  safety_disclosure_person?: string
  safety_disclosure_time?: string
  accept_person?: string
  accept_time?: string
  attendant?: string

  // 审批
  approval_owner_opinion?: string
  approval_owner_sign?: string
  approval_owner_time?: string

  approval_unit_opinion?: string
  approval_unit_sign?: string
  approval_unit_time?: string

  approval_safety_opinion?: string
  approval_safety_sign?: string
  approval_safety_time?: string

  approval_fire_leader_opinion?: string
  approval_fire_leader_sign?: string
  approval_fire_leader_time?: string

  // 动火前当班班长验票
  shift_leader_check_result?: string
  shift_leader_sign?: string
  shift_leader_time?: string

  // 完工验收
  completion_acceptance_result?: string
  completion_acceptance_sign?: string
  completion_acceptance_time?: string

  status?: string
  create_time?: string

  // 允许其它业务字段
  [key: string]: any
}

// 向后兼容 (旧代码可能用 HotWorkPermit 名字)
export type HotWorkPermit = Permit

export interface HotWorkGasAnalysis {
  id?: number
  permit_id?: number
  analysis_round?: number
  sample_time?: string
  representative_gas?: string
  analysis_result?: string
  analyst_name?: string
}

export interface ExtractedSafetyCheck {
  description: string
  is_confirmed: boolean
  confirmed_by?: string
}

export interface PermitUploadResponse {
  permit_type?: PermitType  // 后端返回实际 permit_type
  permit: Permit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
  raw_md: string
  warnings?: Array<{
    type: string
    message: string
  }>
}

export interface PermitSaveRequest {
  permit_type: PermitType
  permit: Permit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
}

export interface ComplianceReviewIssue {
  text: string
  field_key: string
  suggestion: string
  clause?: string  // 法规条款 (GB 30871-2022 第 X.X 条), 可能为空
}

export interface ComplianceReviewItem {
  category: string
  status: 'pass' | 'warning' | 'fail'
  issues: ComplianceReviewIssue[]
}

export interface ComplianceReviewRequest {
  permit_type: PermitType
  permit: Permit
  gas_analyses: HotWorkGasAnalysis[]
  safety_checks: ExtractedSafetyCheck[]
}

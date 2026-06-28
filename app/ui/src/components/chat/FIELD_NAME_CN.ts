// 字段名翻译表 (英文 → 中文)
// 后端 NL2SQL 生成的 SQL 可能用这些字段名, 翻译给业务用户看
// 抽出共享: SmartQuery.tsx 和 HermesChat.tsx 共用
export const FIELD_NAME_CN: Record<string, string> = {
  // top_level CASE 翻译
  '作业类型': '作业类型',
  // 常见统计字段
  'work_date': '日期',
  'work_day': '日期',
  'date': '日期',
  'ticket_count': '作业票数',
  'count': '数量',
  'total': '总数',
  'total_tickets': '作业票总数',
  'special_total': '特殊作业票总数',
  '特殊作业票总数': '特殊作业票总数',
  // 作业类型统计列
  '动火作业': '动火作业',
  '动火': '动火作业',
  '受限空间': '受限空间作业',
  '受限空间作业': '受限空间作业',
  '高处作业': '高处作业',
  '高处': '高处作业',
  '吊装作业': '吊装作业',
  '吊装': '吊装作业',
  '临时用电': '临时用电',
  '临时用电作业': '临时用电',
  '盲板抽堵': '盲板抽堵作业',
  '盲板抽堵作业': '盲板抽堵作业',
  '动土作业': '动土作业',
  '动土': '动土作业',
  '断路作业': '断路作业',
  '断路': '断路作业',
  '设备检维修': '设备检维修',
  // 作业内容
  'content': '作业内容',
  '作业内容': '作业内容',
  'medium': '介质',
  'medium_distribution': '介质分布',
  // 公司
  'company_name': '企业名称',
  'company_code': '企业编码',
  '企业名称': '企业名称',
  // 时间
  'plan_start': '计划开始时间',
  'plan_end': '计划结束时间',
  'actual_start': '实际开始时间',
  'complete_time': '完工时间',
  // 人员
  'task_manager': '作业负责人',
  '作业负责人': '作业负责人',
  'safe_disclose_person': '安全交底人',
  'normal_operator': '操作员',
  'holder_operator': '持票人',
  // 位置/部门
  'ticket_position': '作业位置',
  '作业位置': '作业位置',
  'task_part': '作业部门',
  '作业部门': '作业部门',
  // 其他
  'id': 'ID',
  'n': '数量',
  // 作业小类
  'sub_level': '作业小类',
  '作业小类代码': '作业小类',
  'top_level': '作业类型大类',
}

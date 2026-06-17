/**
 * TicketReviewV2 - 作业票审查 v2
 *
 * 简化版流程:
 * 1) 上传图片/PDF
 * 2) 后端 OCR 识别 (uploadAndExtract) → 返回结构化 JSON
 * 3) 左边原图 + 右边可编辑字段 (用户改 OCR 错的字)
 * 4) 点"合规审查" → 后端调 wiki + LLM
 * 5) 下方展示审查结果
 *
 * 跟 v1 区别:
 * - 不强求矿 U 文本解析, 直接图片 OCR
 * - 不强制规范化字段填写, 全部可编辑
 * - 不做红框高亮, 简化展示
 */
import { useCallback, useRef, useState } from 'react'
import {
  Button,
  Input,
  Textarea,
  makeStyles,
  MessageBar,
  MessageBarBody,
  Spinner,
  Select,
  Text,
  tokens,
  Divider,
  Badge,
} from '@fluentui/react-components'
import { AddRegular, ArrowUploadRegular, CheckmarkRegular } from '@fluentui/react-icons'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import { uploadAndExtract, complianceReview } from '../../services/permitsApi'
import type { ComplianceReviewItem, PermitType } from '../../types/permit'

// react-pdf 需要指定 worker (用 unpkg CDN, 国内可换)
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: 'calc(100vh - 96px)',
    gap: '12px',
  },
  // 顶部工具条
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '8px 0',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  title: { fontSize: '18px', fontWeight: 700, color: tokens.colorBrandForeground1 },

  // 主体两栏
  body: {
    flex: 1,
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
    overflow: 'hidden',
  },

  // 左: 原图
  imagePane: {
    overflow: 'auto',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '8px',
  },
  image: {
    maxWidth: '100%',
    objectFit: 'contain',
  },
  imagePlaceholder: {
    color: tokens.colorNeutralForeground3,
    padding: '60px 20px',
    textAlign: 'center',
  },

  // 右: 可编辑字段
  fieldsPane: {
    overflow: 'auto',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground1,
    padding: '12px 16px',
  },
  fieldGroup: {
    marginBottom: '12px',
  },
  fieldGroupTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: tokens.colorBrandForeground1,
    marginBottom: '6px',
    textTransform: 'uppercase',
  },
  fieldRow: {
    display: 'grid',
    gridTemplateColumns: '120px 1fr',
    gap: '8px',
    alignItems: 'center',
    marginBottom: '6px',
  },
  fieldLabel: {
    fontSize: '12px',
    color: tokens.colorNeutralForeground2,
  },
  fieldInput: {
    fontSize: '13px',
  },

  // 底部: 审查结果
  reviewPane: {
    maxHeight: '40vh',
    overflow: 'auto',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground1,
    padding: '12px 16px',
  },
  reviewCategory: {
    marginBottom: '12px',
    padding: '8px 12px',
    borderRadius: '6px',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  categoryHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '6px',
  },
  statusPass: { backgroundColor: '#e2f9e2', color: '#1a7a1a', padding: '2px 8px', borderRadius: '3px', fontSize: '12px', fontWeight: 600 },
  statusWarn: { backgroundColor: '#fff4ce', color: '#9d5d00', padding: '2px 8px', borderRadius: '3px', fontSize: '12px', fontWeight: 600 },
  statusFail: { backgroundColor: '#fde7e9', color: '#c4314b', padding: '2px 8px', borderRadius: '3px', fontSize: '12px', fontWeight: 600 },
  issueItem: {
    padding: '6px 8px',
    borderBottom: `1px solid ${tokens.colorNeutralStroke3}`,
    fontSize: '13px',
  },
  issueText: { lineHeight: '20px' },
  issueSuggestion: { color: tokens.colorBrandForeground1, marginTop: '4px', fontSize: '12px' },
  issueClause: { color: tokens.colorNeutralForeground3, marginTop: '4px', fontSize: '11px', fontStyle: 'italic' },
  issueFieldTag: { display: 'inline-block', fontSize: '10px', color: tokens.colorNeutralForeground3, backgroundColor: tokens.colorNeutralBackground4, padding: '1px 4px', borderRadius: '3px', marginTop: '2px' },
})

// 不限死字段, 后端识别到什么字段就显示什么
// permit_type 仍然保留, 用于调审查接口

// LLM 提取的英文 key → 中文显示 key 映射 (后端 schema 限定, 前端翻译)
// raw_fields 已经是中文 key, 不需要这个映射
const EN_TO_ZH: Record<string, string> = {
  permit_code: '编号',
  ticket_code: '编号',
  apply_unit: '作业申请单位',
  apply_time: '作业申请时间',
  work_content: '作业内容',
  work_location: '作业地点',
  work_unit: '作业单位',
  work_owner_name: '作业负责人',
  work_owner_phone: '作业负责人电话',
  worker_names: '作业人',
  attendant: '监护人',
  space_name: '受限空间名称',
  original_medium: '原介质',
  risk_identification: '风险辨识',
  related_permit_ids: '关联票证',
  start_time: '开始时间',
  end_time: '结束时间',
  work_level: '作业级别',
  work_method: '作业方式',
  fire_worker_info: '动火人',
  gas_analysis_time: '气体分析时间',
  gas_analyst_name: '分析人',
  gas_analysis_result: '分析结果',
  safety_disclosure_person: '安全交底人',
  safety_disclosure_time: '交底时间',
  accept_person: '接受交底人',
  accept_time: '接受时间',
  approval_owner_opinion: '作业负责人意见',
  approval_owner_sign: '作业负责人签字',
  approval_owner_time: '作业负责人签字时间',
  approval_unit_opinion: '所在单位意见',
  approval_unit_sign: '所在单位签字',
  approval_unit_time: '所在单位签字时间',
  approval_safety_opinion: '安全管理部门意见',
  approval_safety_sign: '安全管理部门签字',
  approval_safety_time: '安全管理部门签字时间',
  approval_fire_leader_opinion: '动火审批人意见',
  approval_fire_leader_sign: '动火审批人签字',
  approval_fire_leader_time: '动火审批人签字时间',
  shift_leader_check_result: '班长验票情况',
  shift_leader_sign: '班长签字',
  shift_leader_time: '班长签字时间',
  completion_acceptance_result: '完工验收',
  completion_acceptance_sign: '验收人签字',
  completion_acceptance_time: '验收时间',
  // 受限空间特殊字段
  equipment_name: '设备名称',
  blind_material: '盲板材质',
  blind_spec: '盲板规格',
  blocking_purpose: '抽堵目的',
  medium_isolation: '隔离置换',
  // 高处作业特殊字段
  work_height: '作业高度',
  fall_protection: '防坠落措施',
  // 吊装作业特殊字段
  lifting_location: '吊装地点',
  lifting_object: '吊装物件',
  lifting_tool_name: '吊具名称',
  command_personnel: '指挥人员',
  lifting_operator: '吊装作业人',
  lifting_method: '吊装方式',
  // 临时用电特殊字段
  power_capacity_limit: '电源接入点',
  working_voltage: '作业电压',
  equipment_rated_power: '用电设备',
  electrical_operator: '用电人',
  work_person: '作业人',
  electrician_cert_number: '作业人电工证号',
  supervisor_cert_number: '负责人电工证号',
  related_permits: '关联票证',
  // 动土作业特殊字段
  work_scope: '作业范围',
  related_explanation_sign: '相关说明签字',
  related_explanation_time: '相关签字时间',
  approval_department_opinion: '多部门会签意见',
  approval_department_sign: '多部门会签签字',
  approval_department_time: '多部门会签签字时间',
  // 断路作业特殊字段
  design_unit: '设计相关单位',
  cutting_reason: '断路原因',
  cutting_description: '断路地段说明',
  approval_fire_safety_opinion: '消防/安全部门意见',
  approval_fire_safety_sign: '消防/安全部门签字',
  approval_fire_safety_time: '消防/安全部门签字时间',
}

// 反向映射: 中文 → 英文 (用于审查时回传给后端)
// 重复中文 key 取第一个英文
const ZH_TO_EN: Record<string, string> = Object.entries(EN_TO_ZH).reduce((acc, [en, zh]) => {
  if (!(zh in acc)) acc[zh] = en
  return acc
}, {} as Record<string, string>)

export default function TicketReviewV2() {
  const classes = useStyles()
  const [permitType, setPermitType] = useState<PermitType>('confined_space')
  const [file, setFile] = useState<File | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})  // 动态字段
  const [gasAnalyses, setGasAnalyses] = useState<Array<Record<string, string>>>([])  // 气体分析
  const [safetyChecks, setSafetyChecks] = useState<Array<Record<string, any>>>([])  // 安全措施
  const [pdfNumPages, setPdfNumPages] = useState<number>(0)
  const [extracting, setExtracting] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewResults, setReviewResults] = useState<ComplianceReviewItem[]>([])
  const [rawMd, setRawMd] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 上传文件
  const handleFileSelect = useCallback((f: File | null) => {
    setError(null)
    if (!f) return
    if (!/\.(pdf|png|jpg|jpeg)$/i.test(f.name)) {
      setError('仅支持 PDF / PNG / JPG')
      return
    }
    setFile(f)
    if (/\.(png|jpg|jpeg)$/i.test(f.name)) {
      setImageUrl(URL.createObjectURL(f))
    } else {
      setImageUrl(null)  // PDF 用 react-pdf 渲染
    }
    setFields({})  // 清空字段, 等待 OCR 填充
    setGasAnalyses([])
    setSafetyChecks([])
    setReviewResults([])
    setRawMd('')
    setPdfNumPages(0)
  }, [permitType])

  // 调后端 OCR 识别
  const handleIdentify = useCallback(async () => {
    if (!file) return
    setExtracting(true)
    setError(null)
    try {
      const result = await uploadAndExtract(file, permitType)
      // result: { permit, gas_analyses, safety_checks, raw_md, raw_fields }
      const permit = result.permit || {}
      const rawFields = result.raw_fields || {}
      // 合并策略:
      // 1) 先用 raw_fields (中文 key, OCR 原文抓的)
      // 2) LLM 提取的 permit (英文 key) 翻译成中文 key 后补上
      // 3) 中文 key 已存在则不覆盖
      const newFields: Record<string, string> = {}
      // 先填 raw_fields (中文 key, 真实 OCR 抓的)
      for (const [key, value] of Object.entries(rawFields)) {
        if (value) newFields[key] = String(value)
      }
      // 再把 permit 的英文 key 翻译成中文
      for (const [enKey, value] of Object.entries(permit)) {
        if (value == null || value === '') continue
        const zhKey = EN_TO_ZH[enKey] || enKey  // 没映射就用英文 key (兜底)
        const strValue = typeof value === 'object' ? JSON.stringify(value) : String(value)
        if (!(zhKey in newFields)) {  // 中文 key 已存在不覆盖
          newFields[zhKey] = strValue
        }
      }
      setFields(newFields)
      setRawMd(result.raw_md || '')
      // 气体分析 + 安全措施
      setGasAnalyses((result.gas_analyses || []).map((g: any) => {
        const r: Record<string, string> = {}
        for (const [k, v] of Object.entries(g)) {
          if (v != null && v !== '') {
            r[EN_TO_ZH[k] || k] = String(v)
          }
        }
        return r
      }))
      setSafetyChecks(result.safety_checks || [])  // 安全措施保留原 description + is_confirmed
    } catch (e: any) {
      setError(e.message || '识别失败')
    } finally {
      setExtracting(false)
    }
  }, [file, permitType])

  // 改字段
  const handleFieldChange = useCallback((key: string, value: string) => {
    setFields(prev => ({ ...prev, [key]: value }))
  }, [])

  // 调合规审查
  const handleReview = useCallback(async () => {
    if (!file) return
    setReviewing(true)
    setError(null)
    try {
      // 把英文字段名反转回中文 (后端 compliance_review 的 JSON schema 期望英文)
      const dataToReview: Record<string, string> = {}
      for (const [zhKey, value] of Object.entries(fields)) {
        // 反向映射: 中文 → 英文
        const enKey = ZH_TO_EN[zhKey] || zhKey
        dataToReview[enKey] = value
      }
      const data = {
        permit_type: permitType,
        data: {
          permit: dataToReview,
          gas_analyses: gasAnalyses.map(g => {
            const r: Record<string, string> = {}
            for (const [zhKey, v] of Object.entries(g)) {
              r[ZH_TO_EN[zhKey] || zhKey] = v
            }
            return r
          }),
          safety_checks: safetyChecks,
        },
      }
      const results = await complianceReview(data)
      setReviewResults(results)
    } catch (e: any) {
      setError(e.message || '审查失败')
    } finally {
      setReviewing(false)
    }
  }, [file, permitType, fields, gasAnalyses, safetyChecks])

  return (
    <div className={classes.root}>
      {/* 顶部工具条 */}
      <div className={classes.toolbar}>
        <Text className={classes.title}>作业票审查 v2</Text>
        <Badge appearance="ghost" color="informative" size="small">图片 + OCR + 叠层编辑</Badge>
        <div style={{ flex: 1 }} />
        <Select
          value={permitType}
          onChange={(_, d) => {
            setPermitType(d.value as PermitType)
            setFields({})
          }}
          style={{ minWidth: 160 }}
        >
          <option value="confined_space">受限空间</option>
          <option value="hot_work">动火</option>
          <option value="blind_plate">盲板抽堵</option>
          <option value="high_above">高处</option>
          <option value="lifting">吊装</option>
          <option value="temp_power">临时用电</option>
          <option value="earthwork">动土</option>
          <option value="road_closure">断路</option>
        </Select>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          style={{ display: 'none' }}
          onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
        />
        <Button
          icon={<ArrowUploadRegular />}
          onClick={() => fileInputRef.current?.click()}
          appearance="subtle"
        >
          选择文件
        </Button>
        <Button
          icon={extracting ? <Spinner size="tiny" /> : <AddRegular />}
          onClick={handleIdentify}
          disabled={!file || extracting}
        >
          {extracting ? '识别中...' : 'OCR 识别'}
        </Button>
        <Button
          icon={reviewing ? <Spinner size="tiny" /> : <CheckmarkRegular />}
          onClick={handleReview}
          disabled={!file || reviewing}
          appearance="primary"
        >
          {reviewing ? '审查中...' : '合规审查'}
        </Button>
      </div>

      {error && (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}

      {/* 主体两栏: 左图, 右字段 */}
      <div className={classes.body}>
        {/* 左侧: 原图 */}
        <div className={classes.imagePane}>
          {file ? (
            <Text size={200} style={{ marginBottom: 8, color: tokens.colorNeutralForeground3 }}>
              📎 {file.name} ({Math.round(file.size / 1024)} KB)
            </Text>
          ) : null}
          {imageUrl ? (
            <img src={imageUrl} alt="作业票" className={classes.image} />
          ) : file?.name.toLowerCase().endsWith('.pdf') ? (
            <div style={{ width: '100%', maxHeight: '70vh', overflow: 'auto' }}>
              <Document
                file={file}
                onLoadSuccess={({ numPages }) => setPdfNumPages(numPages)}
                loading={<Spinner label="加载 PDF..." />}
                error={<MessageBar intent="error"><MessageBarBody>PDF 加载失败</MessageBarBody></MessageBar>}
              >
                {Array.from(new Array(pdfNumPages || 1), (_, index) => (
                  <Page
                    key={`page_${index + 1}`}
                    pageNumber={index + 1}
                    width={700}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                ))}
              </Document>
            </div>
          ) : (
            <div className={classes.imagePlaceholder}>
              请选择作业票图片 (PNG / JPG / PDF)
              <br />
              <Text size={100}>(点上方"选择文件"按钮)</Text>
            </div>
          )}
          {rawMd && (
            <details style={{ marginTop: 12, width: '100%', fontSize: 12 }}>
              <summary style={{ cursor: 'pointer', color: tokens.colorBrandForeground1 }}>
                查看 OCR 原文 (raw_md)
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, maxHeight: 200, overflow: 'auto', marginTop: 8, padding: 8, backgroundColor: tokens.colorNeutralBackground3, borderRadius: 4 }}>
                {rawMd.slice(0, 3000)}
                {rawMd.length > 3000 ? '\n...[截断]' : ''}
              </pre>
            </details>
          )}
        </div>

        {/* 右侧: 可编辑字段 (动态显示) */}
        <div className={classes.fieldsPane}>
          {Object.keys(fields).length === 0 ? (
            <div className={classes.fieldGroup}>
              <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>
                {file ? '⏳ 等待 OCR 识别 (点上方"OCR 识别"按钮)' : '请先选择文件并点"OCR 识别"'}
              </Text>
            </div>
          ) : (
            <div className={classes.fieldGroup}>
              <div className={classes.fieldGroupTitle}>
                识别到的字段 ({Object.keys(fields).length} 个) — 可编辑
              </div>
              {Object.entries(fields).map(([key, value]) => {
                // 长文本用 textarea
                const isLong = String(value).length > 60 || key.includes('content') || key.includes('risk') || key.includes('identification')
                return (
                  <div key={key} className={classes.fieldRow}>
                    <span className={classes.fieldLabel}>{key}</span>
                    {isLong ? (
                      <Textarea
                        className={classes.fieldInput}
                        value={String(value || '')}
                        onChange={(_, d) => handleFieldChange(key, d.value)}
                        rows={2}
                      />
                    ) : (
                      <Input
                        className={classes.fieldInput}
                        value={String(value || '')}
                        onChange={(_, d) => handleFieldChange(key, d.value)}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )}
          <Text size={100} style={{ color: tokens.colorNeutralForeground3, marginTop: 8, display: 'block' }}>
            💡 提示: 后端识别到啥字段就显示啥, 识别错的字直接改即可. 改完点"合规审查"用修正后的数据审查.
          </Text>

          {/* 气体分析 (如果有) */}
          {gasAnalyses.length > 0 && (
            <div className={classes.fieldGroup} style={{ marginTop: 16 }}>
              <div className={classes.fieldGroupTitle}>
                气体分析 ({gasAnalyses.length} 条)
              </div>
              {gasAnalyses.map((g, i) => (
                <div key={i} style={{ padding: '6px 0', borderBottom: `1px dashed ${tokens.colorNeutralStroke3}`, fontSize: 12 }}>
                  <Text weight="semibold" size={200} style={{ color: tokens.colorBrandForeground1 }}>
                    第 {i + 1} 次
                  </Text>
                  {Object.entries(g).map(([k, v]) => (
                    <div key={k} className={classes.fieldRow}>
                      <span className={classes.fieldLabel}>{k}</span>
                      <Input
                        className={classes.fieldInput}
                        value={v}
                        onChange={(_, d) => {
                          const next = [...gasAnalyses]
                          next[i] = { ...next[i], [k]: d.value }
                          setGasAnalyses(next)
                        }}
                      />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* 安全措施 (如果有) */}
          {safetyChecks.length > 0 && (
            <div className={classes.fieldGroup} style={{ marginTop: 16 }}>
              <div className={classes.fieldGroupTitle}>
                安全措施 ({safetyChecks.length} 条) — 勾选确认
              </div>
              {safetyChecks.map((s, i) => (
                <label
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 8,
                    padding: '6px 0',
                    borderBottom: `1px dashed ${tokens.colorNeutralStroke3}`,
                    fontSize: 13,
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!!s.is_confirmed}
                    onChange={(e) => {
                      const next = [...safetyChecks]
                      next[i] = { ...next[i], is_confirmed: e.target.checked }
                      setSafetyChecks(next)
                    }}
                    style={{ marginTop: 3 }}
                  />
                  <span style={{ flex: 1, textDecoration: s.is_confirmed ? 'line-through' : 'none', color: s.is_confirmed ? tokens.colorNeutralForeground3 : tokens.colorNeutralForeground1 }}>
                    {s.description || s.text || JSON.stringify(s)}
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 底部: 审查结果 */}
      {reviewResults.length > 0 && (
        <>
          <Divider />
          <div className={classes.reviewPane}>
            <Text size={400} weight="semibold" style={{ marginBottom: 8 }}>
              合规审查结果
            </Text>
            {reviewResults.map((r, i) => (
              <div key={i} className={classes.reviewCategory}>
                <div className={classes.categoryHeader}>
                  <span className={`${r.status === 'pass' ? classes.statusPass : r.status === 'warning' ? classes.statusWarn : classes.statusFail}`}>
                    {r.status === 'pass' ? '合规' : r.status === 'warning' ? '警告' : '不合规'}
                  </span>
                  <Text weight="semibold" size={200}>{r.category}</Text>
                </div>
                {r.issues.length === 0 ? (
                  <Text size={200} style={{ color: tokens.colorNeutralForeground4 }}>未发现问题</Text>
                ) : (
                  r.issues.map((issue, j) => (
                    <div key={j} className={classes.issueItem}>
                      <div className={classes.issueText}>{issue.text}</div>
                      {issue.suggestion && (
                        <div className={classes.issueSuggestion}>建议：{issue.suggestion}</div>
                      )}
                      {issue.clause && (
                        <div className={classes.issueClause}>📖 {issue.clause}</div>
                      )}
                      <div className={classes.issueFieldTag}>{issue.field_key}</div>
                    </div>
                  ))
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

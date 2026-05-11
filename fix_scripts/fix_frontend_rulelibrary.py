"""
fix_frontend_rulelibrary.py
更新 RuleLibrary.tsx，添加"提示词规则"Tab 展示预设/自定义规则。
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src")


def write_file(rel_path: str, content: str):
    fp = BASE / rel_path
    fp.write_text(content, encoding="utf-8")
    print(f"  WROTE: {rel_path}")


write_file("pages/ruleLibrary/RuleLibrary.tsx", r'''import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Button,
  Text,
  Badge,
  Dialog,
  DialogTrigger,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  Spinner,
  Tab,
  TabList,
  TabValue,
  makeStyles,
  tokens,
  Textarea,
  MessageBar,
  MessageBarBody,
  Input,
  Dropdown,
  Field,
  Option,
} from '@fluentui/react-components'
import {
  ArrowDownloadRegular,
  Copy16Regular,
  DeleteRegular,
  DocumentRegular,
  Edit16Regular,
  EyeRegular,
  SparkleRegular,
  ArrowUploadRegular,
  CloudArrowUpRegular,
  Add16Regular,
} from '@fluentui/react-icons'
import {
  getRuleDocuments,
  uploadRuleDocument,
  deleteRuleDocument as deleteRuleDocApi,
  getRuleDocumentText,
  parseRuleDocument,
} from '../../services/ruleDocsApi'
import {
  getRules,
  createRule,
  updateRule,
  deleteRule,
} from '../../services/api'
import type { RuleDocument } from '../../types/ruleDocument'
import { RuleDocumentSource } from '../../types/ruleDocument'
import type { ReviewRule, CreateRuleRequest } from '../../types/rule'
import { RiskLevel, RuleStatus } from '../../types/rule'

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    height: '100%',
  },
  // Tab
  tabBar: {
    marginBottom: '0',
  },
  // Upload Panel
  uploadPanel: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  uploadCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '16px',
    padding: '32px 24px',
    borderRadius: '12px',
    border: `2px dashed ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground2,
    cursor: 'pointer',
    transitionProperty: 'all',
    transitionDuration: '200ms',
    minHeight: '200px',
    '&:hover': {
      borderColor: tokens.colorBrandStroke1,
      backgroundColor: tokens.colorBrandBackground2,
    },
  },
  uploadIcon: {
    fontSize: '48px',
    color: tokens.colorBrandForeground1,
  },
  uploadText: {
    textAlign: 'center',
    color: tokens.colorNeutralForeground3,
  },
  acceptedFormats: {
    fontSize: '12px',
    color: tokens.colorNeutralForeground4,
  },
  actionRow: {
    display: 'flex',
    gap: '8px',
  },
  // Grid for both tabs
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: '16px',
  },
  // Rule cards
  ruleCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    padding: '16px',
    borderRadius: '12px',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground1,
    transitionProperty: 'all',
    transitionDuration: '150ms',
    '&:hover': {
      borderColor: tokens.colorBrandStroke1,
      boxShadow: tokens.shadow2,
    },
  },
  ruleHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  ruleName: {
    fontWeight: 600,
    fontSize: '14px',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  rulePrompt: {
    fontSize: '12px',
    color: tokens.colorNeutralForeground3,
    lineHeight: '1.5',
    overflow: 'hidden',
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical' as any,
  },
  ruleMeta: {
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  ruleActions: {
    display: 'flex',
    gap: '4px',
    marginTop: 'auto',
  },
  presetBadge: {
    fontSize: '10px',
    color: tokens.colorBrandForeground1,
    border: `1px solid ${tokens.colorBrandStroke1}`,
    padding: '1px 6px',
    borderRadius: '4px',
  },
  // Doc cards
  docCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    padding: '16px',
    borderRadius: '12px',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground1,
    transitionProperty: 'all',
    transitionDuration: '150ms',
    '&:hover': {
      borderColor: tokens.colorBrandStroke1,
      boxShadow: tokens.shadow2,
    },
  },
  docHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  docIcon: {
    fontSize: '24px',
    color: tokens.colorBrandForeground1,
  },
  docName: {
    fontWeight: 600,
    fontSize: '14px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
  },
  docMeta: {
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  docActions: {
    display: 'flex',
    gap: '4px',
    marginTop: 'auto',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    padding: '60px 20px',
    color: tokens.colorNeutralForeground3,
  },
  // Dialog
  dialogSurface: {
    maxWidth: '600px',
  },
  promptPreview: {
    fontFamily: 'monospace',
    fontSize: '12px',
    lineHeight: '1.6',
    padding: '12px',
    backgroundColor: tokens.colorNeutralBackground2,
    borderRadius: '8px',
    maxHeight: '300px',
    overflowY: 'auto',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
  },
  formField: {
    marginBottom: '16px',
  },
})

const riskLevelColors: Record<string, 'danger' | 'warning' | 'success'> = {
  [RiskLevel.High]: 'danger',
  [RiskLevel.Medium]: 'warning',
  [RiskLevel.Low]: 'success',
}

function FileTypeIcon({ fileType }: { fileType: string }) {
  const colors: Record<string, string> = {
    pdf: '#E74C3C',
    docx: '#2980B9',
    md: '#27AE60',
    txt: '#7F8C8D',
  }
  return <DocumentRegular style={{ color: colors[fileType] || tokens.colorBrandForeground1 }} />
}

function SourceBadge({ sourceType }: { sourceType: string }) {
  if (sourceType === RuleDocumentSource.Parsed) {
    return <Badge appearance="filled" color="success" size="small">已解析</Badge>
  }
  return <Badge appearance="outline" color="informative" size="small">上下文注入</Badge>
}

export default function RuleLibrary() {
  const classes = useStyles()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [activeTab, setActiveTab] = useState<TabValue>('rules')

  // Rule documents state
  const [documents, setDocuments] = useState<RuleDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [parsingId, setParsingId] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState<{ name: string; text: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<RuleDocument | null>(null)

  // Rules state
  const [rules, setRules] = useState<ReviewRule[]>([])
  const [loadingRules, setLoadingRules] = useState(true)
  const [previewRule, setPreviewRule] = useState<ReviewRule | null>(null)
  const [editRule, setEditRule] = useState<ReviewRule | null>(null)

  // Rule form state
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formRiskLevel, setFormRiskLevel] = useState<RiskLevel>(RiskLevel.Medium)
  const [saving, setSaving] = useState(false)

  // Delete rule state
  const [deleteRuleTarget, setDeleteRuleTarget] = useState<ReviewRule | null>(null)

  const [error, setError] = useState<string | null>(null)

  const loadDocuments = useCallback(async () => {
    try {
      setLoadingDocs(true)
      const docs = await getRuleDocuments()
      setDocuments(docs)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoadingDocs(false)
    }
  }, [])

  const loadRules = useCallback(async () => {
    try {
      setLoadingRules(true)
      const allRules = await getRules()
      setRules(allRules.filter(r => r.status === RuleStatus.Active))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoadingRules(false)
    }
  }, [])

  useEffect(() => { loadDocuments() }, [loadDocuments])
  useEffect(() => { loadRules() }, [loadRules])

  // Rule document handlers
  const handleUpload = async (file: File) => {
    try { setUploading(true); setError(null); await uploadRuleDocument(file); await loadDocuments() }
    catch (e: any) { setError(e.message) }
    finally { setUploading(false) }
  }

  const handleParse = async (docId: string) => {
    try { setParsingId(docId); setError(null); await parseRuleDocument(docId); await loadDocuments() }
    catch (e: any) { setError(e.message) }
    finally { setParsingId(null) }
  }

  const handleViewText = async (docId: string, name: string) => {
    try { const result = await getRuleDocumentText(docId); setPreviewText({ name, text: result.extracted_text }) }
    catch (e: any) { setError(e.message) }
  }

  const handleDeleteDoc = async (docId: string) => {
    try { setError(null); await deleteRuleDocApi(docId); setDeleteTarget(null); await loadDocuments() }
    catch (e: any) { setError(e.message) }
  }

  // Rule handlers
  function openAddRule() {
    setEditRule(null)
    setFormName(''); setFormDesc(''); setFormPrompt(''); setFormRiskLevel(RiskLevel.Medium)
    setEditRule({ id: '__new__' } as any)
  }

  function openEditRule(rule: ReviewRule) {
    setEditRule(rule)
    setFormName(rule.name); setFormDesc(rule.description); setFormPrompt(rule.prompt || ''); setFormRiskLevel(rule.risk_level)
  }

  async function handleSaveRule() {
    if (!formName.trim() || !formDesc.trim()) { setError('请填写名称和描述'); return }
    setSaving(true); setError(null)
    try {
      const data: CreateRuleRequest = {
        name: formName.trim(),
        description: formDesc.trim(),
        prompt: formPrompt.trim() || null,
        risk_level: formRiskLevel,
      }
      if (editRule && editRule.id !== '__new__') {
        await updateRule(editRule.id, data)
      } else {
        await createRule(data)
      }
      setEditRule(null)
      await loadRules()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function handleDeleteRule(ruleId: string) {
    try { setError(null); await deleteRule(ruleId); setDeleteRuleTarget(null); await loadRules() }
    catch (e: any) { setError(e.message) }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
  }

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation()
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  const handleDownloadTemplate = () => {
    const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? ''
    window.open(`${apiOrigin}/api/v1/rule-documents-template`, '_blank')
  }

  const presetRules = rules.filter(r => r.is_preset)
  const customRules = rules.filter(r => !r.is_preset)

  return (
    <div className={classes.container}>
      <TabList selectedValue={activeTab} onTabSelect={(_, d) => setActiveTab(d.value)} className={classes.tabBar}>
        <Tab value="rules">提示词规则 ({rules.length})</Tab>
        <Tab value="documents">规则文档 ({documents.length})</Tab>
      </TabList>

      {error && (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}

      {/* ====== Tab 1: Prompt Rules ====== */}
      {activeTab === 'rules' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text size={400} weight="semibold">提示词规则</Text>
            <Button icon={<Add16Regular />} size="small" appearance="primary" onClick={openAddRule}>新建规则</Button>
          </div>

          {loadingRules ? (
            <div className={classes.emptyState}><Spinner size="large" /><Text>加载中...</Text></div>
          ) : (
            <>
              {/* Preset Rules */}
              {presetRules.length > 0 && (
                <>
                  <Text size={300} weight="semibold" style={{ color: tokens.colorNeutralForeground3 }}>
                    预设审核规则（可编辑提示词）
                  </Text>
                  <div className={classes.grid}>
                    {presetRules.map(rule => (
                      <div key={rule.id} className={classes.ruleCard}>
                        <div className={classes.ruleHeader}>
                          <Text className={classes.ruleName}>{rule.name}</Text>
                          <Badge appearance="tint" color={riskLevelColors[rule.risk_level]} size="small">{rule.risk_level}</Badge>
                          <span className={classes.presetBadge}>预设</span>
                        </div>
                        <div className={classes.rulePrompt}>{rule.description}</div>
                        <div className={classes.ruleActions}>
                          <Button size="small" appearance="subtle" icon={<EyeRegular />}
                            onClick={() => setPreviewRule(rule)}>预览</Button>
                          <Button size="small" appearance="subtle" icon={<Copy16Regular />}
                            onClick={() => copyToClipboard(rule.prompt || rule.description)}>复制</Button>
                          <Button size="small" appearance="subtle" icon={<Edit16Regular />}
                            onClick={() => openEditRule(rule)}>编辑</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Custom Rules */}
              {customRules.length > 0 && (
                <>
                  <Text size={300} weight="semibold" style={{ color: tokens.colorNeutralForeground3, marginTop: '8px' }}>
                    自定义规则
                  </Text>
                  <div className={classes.grid}>
                    {customRules.map(rule => (
                      <div key={rule.id} className={classes.ruleCard}>
                        <div className={classes.ruleHeader}>
                          <Text className={classes.ruleName}>{rule.name}</Text>
                          <Badge appearance="tint" color={riskLevelColors[rule.risk_level]} size="small">{rule.risk_level}</Badge>
                        </div>
                        <div className={classes.rulePrompt}>{rule.description}</div>
                        <div className={classes.ruleActions}>
                          {rule.prompt && (
                            <Button size="small" appearance="subtle" icon={<EyeRegular />}
                              onClick={() => setPreviewRule(rule)}>预览</Button>
                          )}
                          <Button size="small" appearance="subtle" icon={<Copy16Regular />}
                            onClick={() => copyToClipboard(rule.prompt || rule.description)}>复制</Button>
                          <Button size="small" appearance="subtle" icon={<Edit16Regular />}
                            onClick={() => openEditRule(rule)}>编辑</Button>
                          <Button size="small" appearance="subtle" icon={<DeleteRegular />}
                            onClick={() => setDeleteRuleTarget(rule)} />
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {rules.length === 0 && (
                <div className={classes.emptyState}>
                  <Text>暂无规则，点击"新建规则"创建</Text>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ====== Tab 2: Rule Documents ====== */}
      {activeTab === 'documents' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', height: '100%' }}>
          <div className={classes.uploadPanel}>
            <div
              className={classes.uploadCard}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? (
                <><Spinner size="large" /><Text className={classes.uploadText}>正在上传并提取文本...</Text></>
              ) : (
                <>
                  <CloudArrowUpRegular className={classes.uploadIcon} />
                  <Text className={classes.uploadText}>拖拽规则文档到此处<br />或点击上传</Text>
                  <Text className={classes.acceptedFormats}>支持 PDF / DOCX / Markdown / TXT</Text>
                </>
              )}
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.md,.txt" style={{ display: 'none' }}
                onChange={(e) => { const file = e.target.files?.[0]; if (file) handleUpload(file); e.target.value = '' }} />
            </div>
            <div className={classes.actionRow}>
              <Button icon={<ArrowDownloadRegular />} size="small" onClick={handleDownloadTemplate}>下载模板</Button>
              <Button icon={<ArrowUploadRegular />} size="small" onClick={() => fileInputRef.current?.click()}>上传文件</Button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text size={400} weight="semibold">规则文档库</Text>
              <Button appearance="subtle" size="small" onClick={loadDocuments}>刷新</Button>
            </div>
            {loadingDocs ? (
              <div className={classes.emptyState}><Spinner size="large" /><Text>加载中...</Text></div>
            ) : documents.length === 0 ? (
              <div className={classes.emptyState}>
                <DocumentRegular style={{ fontSize: '48px', color: tokens.colorNeutralForeground4 }} />
                <Text>暂无规则文档，请上传</Text>
              </div>
            ) : (
              <div className={classes.grid}>
                {documents.map((doc) => (
                  <div key={doc.id} className={classes.docCard}>
                    <div className={classes.docHeader}>
                      <FileTypeIcon fileType={doc.file_type} />
                      <Text className={classes.docName} title={doc.name}>{doc.name}</Text>
                    </div>
                    <div className={classes.docMeta}>
                      <Badge appearance="outline" size="small">{doc.file_type.toUpperCase()}</Badge>
                      <SourceBadge sourceType={doc.source_type} />
                    </div>
                    <div className={classes.docActions}>
                      <Button size="small" appearance="subtle" icon={<SparkleRegular />}
                        disabled={parsingId === doc.id} onClick={() => handleParse(doc.id)}>
                        {parsingId === doc.id ? '解析中...' : 'AI 解析'}
                      </Button>
                      <Button size="small" appearance="subtle" icon={<EyeRegular />}
                        onClick={() => handleViewText(doc.id, doc.name)}>查看文本</Button>
                      <Button size="small" appearance="subtle" icon={<DeleteRegular />}
                        onClick={() => setDeleteTarget(doc)} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ====== Dialogs ====== */}

      {/* Prompt Preview Dialog */}
      <Dialog open={!!previewRule} onOpenChange={(_, data) => { if (!data.open) setPreviewRule(null) }}>
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>提示词预览 — {previewRule?.name}</DialogTitle>
            <DialogContent>
              <div className={classes.promptPreview}>
                {previewRule?.prompt || '（无提示词正文）'}
              </div>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" icon={<Copy16Regular />}
                onClick={() => copyToClipboard(previewRule?.prompt || '')}>复制</Button>
              <Button appearance="secondary" onClick={() => setPreviewRule(null)}>关闭</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Rule Edit/Create Dialog */}
      <Dialog open={!!editRule} onOpenChange={(_, data) => { if (!data.open) setEditRule(null) }}>
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>{editRule?.id === '__new__' ? '新建规则' : '编辑规则'}</DialogTitle>
            <DialogContent>
              <Field label="规则名称" required className={classes.formField}>
                <Input value={formName} onChange={(_, d) => setFormName(d.value)} placeholder="例如：气体分析审核" />
              </Field>
              <Field label="规则描述" required className={classes.formField}>
                <Textarea value={formDesc} onChange={(_, d) => setFormDesc(d.value)} placeholder="简要描述该规则的作用" rows={2} />
              </Field>
              <Field label="提示词正文" className={classes.formField}
                hint="完整的审核提示词，审核时会注入到 LLM。支持修改和自定义。">
                <Textarea value={formPrompt} onChange={(_, d) => setFormPrompt(d.value)}
                  placeholder="例如：重点检查气体分析结果是否超标..." rows={6} />
              </Field>
              <Field label="风险等级" className={classes.formField}>
                <Dropdown value={formRiskLevel} selectedOptions={[formRiskLevel]}
                  onOptionSelect={(_, d) => setFormRiskLevel(d.optionValue as RiskLevel)}>
                  <Option value={RiskLevel.High}>高</Option>
                  <Option value={RiskLevel.Medium}>中</Option>
                  <Option value={RiskLevel.Low}>低</Option>
                </Dropdown>
              </Field>
            </DialogContent>
            <DialogActions>
              <Button appearance="primary" onClick={handleSaveRule} disabled={saving}
                icon={saving ? <Spinner size="tiny" /> : undefined}>
                {editRule?.id === '__new__' ? '创建' : '保存'}
              </Button>
              <Button appearance="secondary" onClick={() => setEditRule(null)}>取消</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Delete Rule Dialog */}
      <Dialog open={!!deleteRuleTarget} onOpenChange={(_, data) => { if (!data.open) setDeleteRuleTarget(null) }}>
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>删除规则</DialogTitle>
            <DialogContent>确定要删除规则 "{deleteRuleTarget?.name}" 吗？此操作不可撤销。</DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setDeleteRuleTarget(null)}>取消</Button>
              <Button appearance="primary" onClick={() => deleteRuleTarget && handleDeleteRule(deleteRuleTarget.id)}>删除</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Doc Text Preview Dialog */}
      <Dialog open={!!previewText} onOpenChange={(_, data) => { if (!data.open) setPreviewText(null) }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>文本预览 - {previewText?.name}</DialogTitle>
            <DialogContent>
              <Textarea style={{ width: '100%', maxHeight: '60vh', fontFamily: 'monospace', fontSize: '13px' }}
                value={previewText?.text || ''} readOnly resize="vertical" />
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setPreviewText(null)}>关闭</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Delete Doc Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(_, data) => { if (!data.open) setDeleteTarget(null) }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>确认删除</DialogTitle>
            <DialogContent>确定要删除规则文档 "{deleteTarget?.name}" 吗？此操作不可撤销。</DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button appearance="primary" onClick={() => deleteTarget && handleDeleteDoc(deleteTarget.id)}>删除</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  )
}
''')

print("RuleLibrary.tsx updated!")

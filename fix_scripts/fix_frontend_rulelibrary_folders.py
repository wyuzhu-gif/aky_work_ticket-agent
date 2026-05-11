"""
fix_frontend_rulelibrary_folders.py
更新 RuleLibrary.tsx 支持文件夹管理。
在"提示词规则"Tab 中添加文件夹创建、规则归入文件夹的功能。
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src")

def write_file(rel_path: str, content: str):
    fp = BASE / rel_path
    fp.write_text(content, encoding="utf-8")
    print(f"  WROTE: {rel_path}")

write_file("pages/ruleLibrary/RuleLibrary.tsx", r'''import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Button, Text, Badge, Dialog, DialogSurface, DialogBody, DialogTitle, DialogContent, DialogActions,
  Spinner, Tab, TabList, TabValue, makeStyles, tokens, Textarea, MessageBar, MessageBarBody,
  Input, Field, Dropdown, Option,
} from '@fluentui/react-components'
import {
  ArrowDownloadRegular, Copy16Regular, DeleteRegular, DocumentRegular, Edit16Regular, EyeRegular,
  SparkleRegular, ArrowUploadRegular, CloudArrowUpRegular, Add16Regular, FolderRegular, FolderAddRegular,
} from '@fluentui/react-icons'
import {
  getRuleDocuments, uploadRuleDocument, deleteRuleDocument as deleteRuleDocApi, getRuleDocumentText, parseRuleDocument,
} from '../../services/ruleDocsApi'
import {
  getRules, createRule, updateRule, deleteRule, getFolders, createFolder, updateFolder, deleteFolder as deleteFolderApi,
} from '../../services/api'
import type { RuleDocument } from '../../types/ruleDocument'
import { RuleDocumentSource } from '../../types/ruleDocument'
import type { ReviewRule, CreateRuleRequest, RuleFolder } from '../../types/rule'
import { RiskLevel, RuleStatus } from '../../types/rule'

const useStyles = makeStyles({
  container: { display: 'flex', flexDirection: 'column', gap: '16px', height: '100%' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' },
  ruleCard: { display: 'flex', flexDirection: 'column', gap: '8px', padding: '16px', borderRadius: '12px', border: `1px solid ${tokens.colorNeutralStroke2}`, backgroundColor: tokens.colorNeutralBackground1', '&:hover': { borderColor: tokens.colorBrandStroke1, boxShadow: tokens.shadow2 } },
  ruleHeader: { display: 'flex', alignItems: 'center', gap: '8px' },
  ruleName: { fontWeight: 600, fontSize: '14px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  rulePrompt: { fontSize: '12px', color: tokens.colorNeutralForeground3, lineHeight: '1.5', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' as any },
  ruleMeta: { display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' },
  ruleActions: { display: 'flex', gap: '4px', marginTop: 'auto' },
  presetBadge: { fontSize: '10px', color: tokens.colorBrandForeground1, border: `1px solid ${tokens.colorBrandStroke1}`, padding: '1px 6px', borderRadius: '4px' },
  folderCard: { display: 'flex', flexDirection: 'column', gap: '8px', padding: '16px', borderRadius: '12px', border: `2px solid ${tokens.colorBrandStroke1}`, backgroundColor: tokens.colorBrandBackground2 },
  uploadCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', padding: '32px 24px', borderRadius: '12px', border: `2px dashed ${tokens.colorNeutralStroke2}`, backgroundColor: tokens.colorNeutralBackground2, cursor: 'pointer', minHeight: '200px', '&:hover': { borderColor: tokens.colorBrandStroke1, backgroundColor: tokens.colorBrandBackground2 } },
  uploadIcon: { fontSize: '48px', color: tokens.colorBrandForeground1 },
  uploadText: { textAlign: 'center', color: tokens.colorNeutralForeground3 },
  acceptedFormats: { fontSize: '12px', color: tokens.colorNeutralForeground4 },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', padding: '60px 20px', color: tokens.colorNeutralForeground3 },
  dialogSurface: { maxWidth: '600px' },
  promptPreview: { fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.6', padding: '12px', backgroundColor: tokens.colorNeutralBackground2, borderRadius: '8px', maxHeight: '300px', overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
  formField: { marginBottom: '16px' },
  docCard: { display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', borderRadius: '12px', border: `1px solid ${tokens.colorNeutralStroke2}`, backgroundColor: tokens.colorNeutralBackground1, '&:hover': { borderColor: tokens.colorBrandStroke1, boxShadow: tokens.shadow2 } },
})

const riskLevelColors: Record<string, 'danger' | 'warning' | 'success'> = {
  [RiskLevel.High]: 'danger', [RiskLevel.Medium]: 'warning', [RiskLevel.Low]: 'success',
}

function FileTypeIcon({ fileType }: { fileType: string }) {
  const c: Record<string, string> = { pdf: '#E74C3C', docx: '#2980B9', md: '#27AE60', txt: '#7F8C8D' }
  return <DocumentRegular style={{ color: c[fileType] || tokens.colorBrandForeground1 }} />
}
function SourceBadge({ sourceType }: { sourceType: string }) {
  return sourceType === RuleDocumentSource.Parsed
    ? <Badge appearance="filled" color="success" size="small">已解析</Badge>
    : <Badge appearance="outline" color="informative" size="small">上下文注入</Badge>
}

export default function RuleLibrary() {
  const classes = useStyles()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [activeTab, setActiveTab] = useState<TabValue>('rules')

  // Docs state
  const [documents, setDocuments] = useState<RuleDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [parsingId, setParsingId] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState<{ name: string; text: string } | null>(null)

  // Rules state
  const [rules, setRules] = useState<ReviewRule[]>([])
  const [folders, setFolders] = useState<RuleFolder[]>([])
  const [loadingRules, setLoadingRules] = useState(true)
  const [previewRule, setPreviewRule] = useState<ReviewRule | null>(null)
  const [editRule, setEditRule] = useState<ReviewRule | null>(null)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formFolderId, setFormFolderId] = useState<string | null>(null)
  const [formRiskLevel, setFormRiskLevel] = useState<RiskLevel>(RiskLevel.Medium)
  const [saving, setSaving] = useState(false)

  // Folder create dialog
  const [folderDialogOpen, setFolderDialogOpen] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [folderDesc, setFolderDesc] = useState('')

  // Move rule to folder dialog
  const [moveRuleTarget, setMoveRuleTarget] = useState<ReviewRule | null>(null)
  const [moveToFolderId, setMoveToFolderId] = useState<string | null>(null)

  // Delete states
  const [deleteRuleTarget, setDeleteRuleTarget] = useState<ReviewRule | null>(null)
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<RuleFolder | null>(null)
  const [deleteDocTarget, setDeleteDocTarget] = useState<RuleDocument | null>(null)

  const [error, setError] = useState<string | null>(null)

  const loadDocs = useCallback(async () => { try { setLoadingDocs(true); setDocuments(await getRuleDocuments()) } catch (e: any) { setError(e.message) } finally { setLoadingDocs(false) } }, [])
  const loadRules = useCallback(async () => {
    try { setLoadingRules(true); const [r, f] = await Promise.all([getRules(), getFolders()]); setRules(r.filter(x => x.status === RuleStatus.Active)); setFolders(f) }
    catch (e: any) { setError(e.message) } finally { setLoadingRules(false) }
  }, [])
  useEffect(() => { loadDocs() }, [loadDocs])
  useEffect(() => { loadRules() }, [loadRules])

  // Handlers
  const handleUpload = async (file: File) => { try { setUploading(true); setError(null); await uploadRuleDocument(file); await loadDocs() } catch (e: any) { setError(e.message) } finally { setUploading(false) } }
  const handleParse = async (id: string) => { try { setParsingId(id); setError(null); await parseRuleDocument(id); await loadDocs() } catch (e: any) { setError(e.message) } finally { setParsingId(null) } }
  const handleViewText = async (id: string, name: string) => { try { const r = await getRuleDocumentText(id); setPreviewText({ name, text: r.extracted_text }) } catch (e: any) { setError(e.message) } }
  const handleDeleteDoc = async (id: string) => { try { setError(null); await deleteRuleDocApi(id); setDeleteDocTarget(null); await loadDocs() } catch (e: any) { setError(e.message) } }

  function openAddRule() { setEditRule({ id: '__new__' } as any); setFormName(''); setFormDesc(''); setFormPrompt(''); setFormFolderId(null); setFormRiskLevel(RiskLevel.Medium) }
  function openEditRule(rule: ReviewRule) { setEditRule(rule); setFormName(rule.name); setFormDesc(rule.description); setFormPrompt(rule.prompt || ''); setFormFolderId(rule.folder_id); setFormRiskLevel(rule.risk_level) }
  async function handleSaveRule() {
    if (!formName.trim() || !formDesc.trim()) { setError('请填写名称和描述'); return }
    setSaving(true); setError(null)
    try {
      const data: CreateRuleRequest = { name: formName.trim(), description: formDesc.trim(), prompt: formPrompt.trim() || null, folder_id: formFolderId, risk_level: formRiskLevel }
      if (editRule && editRule.id !== '__new__') await updateRule(editRule.id, data); else await createRule(data)
      setEditRule(null); await loadRules()
    } catch (e: any) { setError(e.message) } finally { setSaving(false) }
  }
  async function handleDeleteRule(id: string) { try { setError(null); await deleteRule(id); setDeleteRuleTarget(null); await loadRules() } catch (e: any) { setError(e.message) } }

  async function handleCreateFolder() {
    if (!folderName.trim()) return
    setSaving(true); setError(null)
    try { await createFolder({ name: folderName.trim(), description: folderDesc.trim() || null }); setFolderDialogOpen(false); setFolderName(''); setFolderDesc(''); await loadRules() }
    catch (e: any) { setError(e.message) } finally { setSaving(false) }
  }
  async function handleDeleteFolder(id: string) { try { setError(null); await deleteFolderApi(id); setDeleteFolderTarget(null); await loadRules() } catch (e: any) { setError(e.message) } }

  async function handleMoveRule() {
    if (!moveRuleTarget) return
    try { setError(null); await updateRule(moveRuleTarget.id, { folder_id: moveToFolderId }); setMoveRuleTarget(null); await loadRules() }
    catch (e: any) { setError(e.message) }
  }

  const copyToClipboard = (text: string) => navigator.clipboard.writeText(text)
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer.files?.[0]; if (f) handleUpload(f) }
  const handleDownloadTemplate = () => { const o = import.meta.env.VITE_API_ORIGIN ?? ''; window.open(`${o}/api/v1/rule-documents-template`, '_blank') }

  // Group rules
  const rulesByFolder = new Map<string, ReviewRule[]>()
  const uncategorized: ReviewRule[] = []
  for (const r of rules) { if (r.folder_id) { const a = rulesByFolder.get(r.folder_id) || []; a.push(r); rulesByFolder.set(r.folder_id, a) } else uncategorized.push(r) }

  const renderRuleCard = (rule: ReviewRule) => (
    <div key={rule.id} className={classes.ruleCard}>
      <div className={classes.ruleHeader}>
        <Text className={classes.ruleName}>{rule.name}</Text>
        <Badge appearance="tint" color={riskLevelColors[rule.risk_level]} size="small">{rule.risk_level}</Badge>
        {rule.is_preset && <span className={classes.presetBadge}>预设</span>}
      </div>
      <div className={classes.rulePrompt}>{rule.description}</div>
      <div className={classes.ruleActions}>
        {rule.prompt && <Button size="small" appearance="subtle" icon={<EyeRegular />} onClick={() => setPreviewRule(rule)}>预览</Button>}
        <Button size="small" appearance="subtle" icon={<Copy16Regular />} onClick={() => copyToClipboard(rule.prompt || rule.description)}>复制</Button>
        <Button size="small" appearance="subtle" icon={<Edit16Regular />} onClick={() => openEditRule(rule)}>编辑</Button>
        <Button size="small" appearance="subtle" onClick={() => { setMoveRuleTarget(rule); setMoveToFolderId(rule.folder_id) }} title="移动到文件夹">
          <FolderRegular />
        </Button>
        {!rule.is_preset && <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => setDeleteRuleTarget(rule)} />}
      </div>
    </div>
  )

  return (
    <div className={classes.container}>
      <TabList selectedValue={activeTab} onTabSelect={(_, d) => setActiveTab(d.value)}>
        <Tab value="rules">提示词规则 ({rules.length})</Tab>
        <Tab value="documents">规则文档 ({documents.length})</Tab>
      </TabList>
      {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}

      {/* ====== Tab 1: Rules + Folders ====== */}
      {activeTab === 'rules' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text size={400} weight="semibold">提示词规则</Text>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button icon={<FolderAddRegular />} size="small" appearance="secondary" onClick={() => setFolderDialogOpen(true)}>新建文件夹</Button>
              <Button icon={<Add16Regular />} size="small" appearance="primary" onClick={openAddRule}>新建规则</Button>
            </div>
          </div>

          {loadingRules ? <div className={classes.emptyState}><Spinner size="large" /></div> : (<>
            {/* Folders */}
            {folders.map(f => {
              const fr = rulesByFolder.get(f.id) || []
              return (
                <div key={f.id} className={classes.folderCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <FolderRegular style={{ fontSize: '20px', color: tokens.colorBrandForeground1 }} />
                      <Text weight="semibold" size={400}>{f.name}</Text>
                      {f.description && <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>{f.description}</Text>}
                      <Badge appearance="outline" size="small">{fr.length} 条规则</Badge>
                    </div>
                    <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => setDeleteFolderTarget(f)} />
                  </div>
                  {fr.length > 0 ? <div className={classes.grid}>{fr.map(renderRuleCard)}</div>
                    : <Text size={200} style={{ color: tokens.colorNeutralForeground4, padding: '8px' }}>将规则拖入此文件夹，或编辑规则时选择此文件夹</Text>}
                </div>
              )
            })}

            {/* Uncategorized rules */}
            {uncategorized.length > 0 && (<>
              {folders.length > 0 && <Text size={300} weight="semibold" style={{ color: tokens.colorNeutralForeground3, marginTop: '8px' }}>未分类规则</Text>}
              <div className={classes.grid}>{uncategorized.map(renderRuleCard)}</div>
            </>)}

            {rules.length === 0 && <div className={classes.emptyState}><Text>暂无规则</Text></div>}
          </>)}
        </div>
      )}

      {/* ====== Tab 2: Rule Documents ====== */}
      {activeTab === 'documents' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', height: '100%' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className={classes.uploadCard} onDragOver={handleDragOver} onDrop={handleDrop} onClick={() => fileInputRef.current?.click()}>
              {uploading ? <><Spinner size="large" /><Text className={classes.uploadText}>上传中...</Text></>
                : <><CloudArrowUpRegular className={classes.uploadIcon} /><Text className={classes.uploadText}>拖拽文档到此处<br />或点击上传</Text><Text className={classes.acceptedFormats}>PDF / DOCX / Markdown / TXT</Text></>}
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.md,.txt" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = '' }} />
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button icon={<ArrowDownloadRegular />} size="small" onClick={handleDownloadTemplate}>下载模板</Button>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text size={400} weight="semibold">规则文档库</Text>
              <Button appearance="subtle" size="small" onClick={loadDocs}>刷新</Button>
            </div>
            {loadingDocs ? <div className={classes.emptyState}><Spinner size="large" /></div>
              : documents.length === 0 ? <div className={classes.emptyState}><DocumentRegular style={{ fontSize: '48px', color: tokens.colorNeutralForeground4 }} /><Text>暂无文档</Text></div>
              : <div className={classes.grid}>{documents.map(doc => (
                <div key={doc.id} className={classes.docCard}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <FileTypeIcon fileType={doc.file_type} />
                    <Text style={{ fontWeight: 600, fontSize: '14px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.name}</Text>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <Badge appearance="outline" size="small">{doc.file_type.toUpperCase()}</Badge>
                    <SourceBadge sourceType={doc.source_type} />
                  </div>
                  <div style={{ display: 'flex', gap: '4px', marginTop: 'auto' }}>
                    <Button size="small" appearance="subtle" icon={<SparkleRegular />} disabled={parsingId === doc.id} onClick={() => handleParse(doc.id)}>{parsingId === doc.id ? '解析中...' : 'AI 解析'}</Button>
                    <Button size="small" appearance="subtle" icon={<EyeRegular />} onClick={() => handleViewText(doc.id, doc.name)}>查看</Button>
                    <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => setDeleteDocTarget(doc)} />
                  </div>
                </div>
              ))}</div>
            }
          </div>
        </div>
      )}

      {/* ====== Dialogs ====== */}

      {/* Preview */}
      <Dialog open={!!previewRule} onOpenChange={(_, d) => { if (!d.open) setPreviewRule(null) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>提示词预览 — {previewRule?.name}</DialogTitle>
          <DialogContent><div className={classes.promptPreview}>{previewRule?.prompt || '（无）'}</div></DialogContent>
          <DialogActions>
            <Button appearance="secondary" icon={<Copy16Regular />} onClick={() => copyToClipboard(previewRule?.prompt || '')}>复制</Button>
            <Button appearance="secondary" onClick={() => setPreviewRule(null)}>关闭</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Rule Edit/Create */}
      <Dialog open={!!editRule} onOpenChange={(_, d) => { if (!d.open) setEditRule(null) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>{editRule?.id === '__new__' ? '新建规则' : '编辑规则'}</DialogTitle>
          <DialogContent>
            <Field label="规则名称" required className={classes.formField}><Input value={formName} onChange={(_, d) => setFormName(d.value)} /></Field>
            <Field label="描述" required className={classes.formField}><Textarea value={formDesc} onChange={(_, d) => setFormDesc(d.value)} rows={2} /></Field>
            <Field label="提示词正文" className={classes.formField} hint="审核时注入 LLM 的完整提示词">
              <Textarea value={formPrompt} onChange={(_, d) => setFormPrompt(d.value)} rows={6} />
            </Field>
            <Field label="所属文件夹" className={classes.formField}>
              <Dropdown placeholder="未分类" selectedOptions={formFolderId ? [formFolderId] : []}
                onOptionSelect={(_, d) => setFormFolderId(d.optionValue === '__none__' ? null : d.optionValue)}>
                <Option value="__none__">未分类</Option>
                {folders.map(f => <Option key={f.id} value={f.id}>{f.name}</Option>)}
              </Dropdown>
            </Field>
            <Field label="风险等级" className={classes.formField}>
              <Dropdown value={formRiskLevel} selectedOptions={[formRiskLevel]} onOptionSelect={(_, d) => setFormRiskLevel(d.optionValue as RiskLevel)}>
                <Option value={RiskLevel.High}>高</Option><Option value={RiskLevel.Medium}>中</Option><Option value={RiskLevel.Low}>低</Option>
              </Dropdown>
            </Field>
          </DialogContent>
          <DialogActions>
            <Button appearance="primary" onClick={handleSaveRule} disabled={saving} icon={saving ? <Spinner size="tiny" /> : undefined}>{editRule?.id === '__new__' ? '创建' : '保存'}</Button>
            <Button appearance="secondary" onClick={() => setEditRule(null)}>取消</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Create Folder */}
      <Dialog open={folderDialogOpen} onOpenChange={(_, d) => { if (!d.open) setFolderDialogOpen(false) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>新建文件夹</DialogTitle>
          <DialogContent>
            <Field label="文件夹名称" required className={classes.formField}><Input value={folderName} onChange={(_, d) => setFolderName(d.value)} placeholder="例如：安全审核规则集" /></Field>
            <Field label="描述" className={classes.formField}><Textarea value={folderDesc} onChange={(_, d) => setFolderDesc(d.value)} placeholder="可选描述" rows={2} /></Field>
          </DialogContent>
          <DialogActions>
            <Button appearance="primary" onClick={handleCreateFolder} disabled={saving}>{saving ? '创建中...' : '创建'}</Button>
            <Button appearance="secondary" onClick={() => setFolderDialogOpen(false)}>取消</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Move Rule to Folder */}
      <Dialog open={!!moveRuleTarget} onOpenChange={(_, d) => { if (!d.open) setMoveRuleTarget(null) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>移动规则到文件夹</DialogTitle>
          <DialogContent>
            <Text>将 "{moveRuleTarget?.name}" 移动到：</Text>
            <Field className={classes.formField} style={{ marginTop: '12px' }}>
              <Dropdown placeholder="未分类" selectedOptions={moveToFolderId ? [moveToFolderId] : []}
                onOptionSelect={(_, d) => setMoveToFolderId(d.optionValue === '__none__' ? null : d.optionValue)}>
                <Option value="__none__">未分类</Option>
                {folders.map(f => <Option key={f.id} value={f.id}>{f.name}</Option>)}
              </Dropdown>
            </Field>
          </DialogContent>
          <DialogActions>
            <Button appearance="primary" onClick={handleMoveRule}>确认</Button>
            <Button appearance="secondary" onClick={() => setMoveRuleTarget(null)}>取消</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Delete Rule */}
      <Dialog open={!!deleteRuleTarget} onOpenChange={(_, d) => { if (!d.open) setDeleteRuleTarget(null) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>删除规则</DialogTitle>
          <DialogContent>确定删除 "{deleteRuleTarget?.name}" 吗？</DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={() => setDeleteRuleTarget(null)}>取消</Button>
            <Button appearance="primary" onClick={() => deleteRuleTarget && handleDeleteRule(deleteRuleTarget.id)}>删除</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Delete Folder */}
      <Dialog open={!!deleteFolderTarget} onOpenChange={(_, d) => { if (!d.open) setDeleteFolderTarget(null) }}>
        <DialogSurface className={classes.dialogSurface}><DialogBody>
          <DialogTitle>删除文件夹</DialogTitle>
          <DialogContent>确定删除文件夹 "{deleteFolderTarget?.name}" 吗？文件夹内的规则不会被删除，只会变为未分类。</DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={() => setDeleteFolderTarget(null)}>取消</Button>
            <Button appearance="primary" onClick={() => deleteFolderTarget && handleDeleteFolder(deleteFolderTarget.id)}>删除</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Delete Doc */}
      <Dialog open={!!deleteDocTarget} onOpenChange={(_, d) => { if (!d.open) setDeleteDocTarget(null) }}>
        <DialogSurface><DialogBody>
          <DialogTitle>确认删除</DialogTitle>
          <DialogContent>确定删除 "{deleteDocTarget?.name}" 吗？</DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={() => setDeleteDocTarget(null)}>取消</Button>
            <Button appearance="primary" onClick={() => deleteDocTarget && handleDeleteDoc(deleteDocTarget.id)}>删除</Button>
          </DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>

      {/* Doc Text Preview */}
      <Dialog open={!!previewText} onOpenChange={(_, d) => { if (!d.open) setPreviewText(null) }}>
        <DialogSurface><DialogBody>
          <DialogTitle>文本预览 - {previewText?.name}</DialogTitle>
          <DialogContent><Textarea style={{ width: '100%', maxHeight: '60vh', fontFamily: 'monospace', fontSize: '13px' }} value={previewText?.text || ''} readOnly resize="vertical" /></DialogContent>
          <DialogActions><Button appearance="secondary" onClick={() => setPreviewText(null)}>关闭</Button></DialogActions>
        </DialogBody></DialogSurface>
      </Dialog>
    </div>
  )
}
''')

print("RuleLibrary.tsx updated with folder management!")

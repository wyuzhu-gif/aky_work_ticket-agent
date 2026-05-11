"""
fix_frontend_folder_panels.py
更新 RuleLibrary.tsx 和 RulesPanel.tsx 支持文件夹功能。
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src")

def write_file(rel_path: str, content: str):
    fp = BASE / rel_path
    fp.write_text(content, encoding="utf-8")
    print(f"  WROTE: {rel_path}")

# ========== components/RulesPanel.tsx ==========
# Updated: adds folder quick-select above individual rules
write_file("components/RulesPanel.tsx", r'''import {
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Dropdown,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Textarea,
  makeStyles,
  tokens,
  Tooltip,
  Divider,
} from '@fluentui/react-components'
import { Add16Regular, Copy16Regular, Delete16Regular, Edit16Regular, Eye16Regular, FolderRegular } from '@fluentui/react-icons'
import { useEffect, useState } from 'react'
import {
  getRules,
  createRule,
  updateRule,
  deleteRule,
  getDocumentRules,
  setDocumentRule,
  getFolders,
} from '../services/api'
import type { ReviewRule, RuleExample, CreateRuleRequest, DocumentRuleAssociation, RuleFolder } from '../types/rule'
import { RiskLevel, RuleStatus } from '../types/rule'

const useStyles = makeStyles({
  presetBadge: { fontSize: '10px', color: tokens.colorBrandForeground1, border: `1px solid ${tokens.colorBrandStroke1}`, padding: '1px 6px', borderRadius: '4px' },
  promptPreview: { fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.6', padding: '12px', backgroundColor: tokens.colorNeutralBackground2, borderRadius: '8px', maxHeight: '200px', overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
  dialogSurface: { backgroundColor: tokens.colorNeutralBackground1, border: `1px solid ${tokens.colorNeutralStroke2}`, borderRadius: '12px', maxWidth: '600px', zIndex: 1000000 },
  formField: { marginBottom: '16px' },
  exampleSection: { marginTop: '16px', padding: '12px', backgroundColor: tokens.colorNeutralBackground2, borderRadius: '8px' },
  exampleItem: { display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' },
  exampleInput: { flex: 1 },
  folderRow: { display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', cursor: 'pointer', borderRadius: '6px', '&:hover': { backgroundColor: tokens.colorNeutralBackground2 } },
  folderSelected: { backgroundColor: tokens.colorBrandBackground2 },
  sectionLabel: { fontSize: '11px', fontWeight: 600, color: tokens.colorNeutralForeground3, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '6px 14px' },
})

const riskLevelColors: Record<RiskLevel, 'danger' | 'warning' | 'success'> = {
  [RiskLevel.High]: 'danger',
  [RiskLevel.Medium]: 'warning',
  [RiskLevel.Low]: 'success',
}

interface RulesPanelProps {
  docId: string
  enabledRuleIds: string[]
  onEnabledRulesChange: (ruleIds: string[]) => void
  onRulesCountChange?: (count: number) => void
  hideHeader?: boolean
}

export function RulesPanel({ docId, enabledRuleIds, onEnabledRulesChange, onRulesCountChange, hideHeader = false }: RulesPanelProps) {
  const classes = useStyles()
  const [rules, setRules] = useState<ReviewRule[]>([])
  const [folders, setFolders] = useState<RuleFolder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<ReviewRule | null>(null)
  const [saving, setSaving] = useState(false)
  const [previewRule, setPreviewRule] = useState<ReviewRule | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formRiskLevel, setFormRiskLevel] = useState<RiskLevel>(RiskLevel.Medium)
  const [formExamples, setFormExamples] = useState<RuleExample[]>([])

  useEffect(() => { loadData() }, [docId])

  async function loadData() {
    setLoading(true); setError(undefined)
    try {
      const [allRules, docRules, allFolders] = await Promise.all([getRules(), getDocumentRules(docId), getFolders()])
      const activeRules = allRules.filter(r => r.status === RuleStatus.Active)
      setRules(activeRules); setFolders(allFolders)
      onRulesCountChange?.(activeRules.length)
      const enabledIds = docRules.filter((a: DocumentRuleAssociation) => a.enabled).map((a: DocumentRuleAssociation) => a.rule_id)
      onEnabledRulesChange(enabledIds)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }

  async function handleToggleRule(ruleId: string, enabled: boolean) {
    try {
      await setDocumentRule(docId, ruleId, enabled)
      onEnabledRulesChange(enabled ? [...enabledRuleIds, ruleId] : enabledRuleIds.filter(id => id !== ruleId))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function handleSelectFolder(folderId: string) {
    const folderRules = rules.filter(r => r.folder_id === folderId)
    const toEnable = folderRules.filter(r => !enabledRuleIds.includes(r.id))
    try {
      for (const r of toEnable) await setDocumentRule(docId, r.id, true)
      const allIds = [...new Set([...enabledRuleIds, ...toEnable.map(r => r.id)])]
      onEnabledRulesChange(allIds)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  async function handleDeselectFolder(folderId: string) {
    const folderRuleIds = rules.filter(r => r.folder_id === folderId).map(r => r.id)
    try {
      for (const rid of folderRuleIds) await setDocumentRule(docId, rid, false)
      onEnabledRulesChange(enabledRuleIds.filter(id => !folderRuleIds.includes(id)))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }

  function openAddDialog() { setEditingRule(null); setFormName(''); setFormDesc(''); setFormPrompt(''); setFormRiskLevel(RiskLevel.Medium); setFormExamples([]); setDialogOpen(true) }
  function openEditDialog(rule: ReviewRule) { setEditingRule(rule); setFormName(rule.name); setFormDesc(rule.description); setFormPrompt(rule.prompt || ''); setFormRiskLevel(rule.risk_level); setFormExamples(rule.examples || []); setDialogOpen(true) }

  async function handleSave() {
    if (!formName.trim() || !formDesc.trim()) { setError('请填写规则名称和描述'); return }
    setSaving(true); setError(undefined)
    try {
      const data: CreateRuleRequest = { name: formName.trim(), description: formDesc.trim(), prompt: formPrompt.trim() || null, risk_level: formRiskLevel, examples: formExamples.filter(e => e.text.trim()) }
      if (editingRule) await updateRule(editingRule.id, data); else await createRule(data)
      setDialogOpen(false); await loadData()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSaving(false) }
  }

  function openDeleteDialog(ruleId: string) { setDeletingRuleId(ruleId); setDeleteDialogOpen(true) }
  async function handleConfirmDelete() {
    if (!deletingRuleId) return; setDeleting(true)
    try { await deleteRule(deletingRuleId); await loadData(); setDeleteDialogOpen(false); setDeletingRuleId(null) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setDeleting(false) }
  }

  function addExample() { setFormExamples([...formExamples, { text: '', explanation: '' }]) }
  function updateExample(index: number, field: keyof RuleExample, value: string) { const u = [...formExamples]; u[index] = { ...u[index], [field]: value }; setFormExamples(u) }
  function removeExample(index: number) { setFormExamples(formExamples.filter((_, i) => i !== index)) }
  function copyPrompt(rule: ReviewRule) { navigator.clipboard.writeText(rule.prompt || rule.description) }

  // Group rules by folder
  const rulesByFolder = new Map<string, ReviewRule[]>()
  const uncategorized: ReviewRule[] = []
  for (const r of rules) {
    if (r.folder_id) {
      const arr = rulesByFolder.get(r.folder_id) || []
      arr.push(r)
      rulesByFolder.set(r.folder_id, arr)
    } else {
      uncategorized.push(r)
    }
  }

  const isFolderFullyEnabled = (folderId: string) => {
    const fr = rulesByFolder.get(folderId) || []
    return fr.length > 0 && fr.every(r => enabledRuleIds.includes(r.id))
  }

  const renderRule = (rule: ReviewRule) => (
    <div key={rule.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 14px', borderBottom: `1px solid ${tokens.colorNeutralStroke2}` }}>
      <Checkbox checked={enabledRuleIds.includes(rule.id)} onChange={(_, d) => handleToggleRule(rule.id, !!d.checked)} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '12px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
          {rule.name}
          <Badge appearance="tint" color={riskLevelColors[rule.risk_level]} size="small">{rule.risk_level}</Badge>
          {rule.is_preset && <span className={classes.presetBadge}>预设</span>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: '2px', opacity: 0.7 }}>
        {rule.prompt && <Button size="small" appearance="subtle" icon={<Eye16Regular />} onClick={() => setPreviewRule(rule)} />}
        <Button size="small" appearance="subtle" icon={<Copy16Regular />} onClick={() => copyPrompt(rule)} />
        <Button size="small" appearance="subtle" icon={<Edit16Regular />} onClick={() => openEditDialog(rule)} />
        {!rule.is_preset && <Button size="small" appearance="subtle" icon={<Delete16Regular />} onClick={() => openDeleteDialog(rule.id)} />}
      </div>
    </div>
  )

  const compactContent = (
    <>
      {error && <MessageBar intent="error" style={{ margin: '8px' }}><MessageBarBody>{error}</MessageBarBody></MessageBar>}
      {loading ? <div style={{ padding: '16px', textAlign: 'center' }}><Spinner size="small" /></div> : (
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {/* Folder quick-select */}
          {folders.length > 0 && <>
            <div className={classes.sectionLabel}>文件夹（点击全选）</div>
            {folders.map(f => {
              const fr = rulesByFolder.get(f.id) || []
              const allOn = isFolderFullyEnabled(f.id)
              return (
                <div key={f.id}
                  className={`${classes.folderRow} ${allOn ? classes.folderSelected : ''}`}
                  onClick={() => allOn ? handleDeselectFolder(f.id) : handleSelectFolder(f.id)}
                >
                  <FolderRegular style={{ fontSize: '16px', color: tokens.colorBrandForeground1 }} />
                  <span style={{ flex: 1, fontSize: '12px', fontWeight: 500 }}>{f.name}</span>
                  <Badge appearance="outline" size="small">{fr.length} 条规则</Badge>
                  {allOn && <Badge appearance="tint" color="success" size="small">已全选</Badge>}
                </div>
              )
            })}
            <Divider style={{ margin: '4px 0' }} />
          </>}

          {/* Individual rules by folder */}
          {folders.map(f => {
            const fr = rulesByFolder.get(f.id)
            if (!fr || fr.length === 0) return null
            return (
              <div key={f.id}>
                <div className={classes.sectionLabel} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <FolderRegular style={{ fontSize: '12px' }} /> {f.name}
                </div>
                {fr.map(renderRule)}
              </div>
            )
          })}

          {/* Uncategorized rules */}
          {uncategorized.length > 0 && (folders.length > 0 && <div className={classes.sectionLabel}>未分类规则</div>)}
          {uncategorized.map(renderRule)}

          {rules.length === 0 && <div style={{ padding: '16px', textAlign: 'center', color: tokens.colorNeutralForeground3, fontSize: '12px' }}>暂无规则</div>}
          <div style={{ padding: '8px 14px' }}>
            <Button size="small" appearance="subtle" icon={<Add16Regular />} onClick={openAddDialog}>添加规则</Button>
          </div>
        </div>
      )}
    </>
  )

  return (
    <>
      {hideHeader ? compactContent : <Card style={{ borderRadius: '12px', border: `1px solid ${tokens.colorNeutralStroke2}` }}>{compactContent}</Card>}

      {/* Preview Dialog */}
      <Dialog open={!!previewRule} onOpenChange={(_, d) => { if (!d.open) setPreviewRule(null) }}>
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>提示词预览 — {previewRule?.name}</DialogTitle>
            <DialogContent><div className={classes.promptPreview}>{previewRule?.prompt || '（无）'}</div></DialogContent>
            <DialogActions>
              <Button appearance="secondary" icon={<Copy16Regular />} onClick={() => copyPrompt(previewRule!)}>复制</Button>
              <Button appearance="secondary" onClick={() => setPreviewRule(null)}>关闭</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(_, d) => setDialogOpen(d.open)} modalType="modal">
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>{editingRule ? '编辑规则' : '添加规则'}</DialogTitle>
            <DialogContent>
              <Field label="规则名称" required className={classes.formField}><Input value={formName} onChange={(_, d) => setFormName(d.value)} placeholder="例如：敏感词检测" /></Field>
              <Field label="规则描述" required className={classes.formField}><Textarea value={formDesc} onChange={(_, d) => setFormDesc(d.value)} placeholder="描述该规则检测的问题类型..." rows={2} /></Field>
              <Field label="提示词正文" className={classes.formField} hint="完整的审核提示词，审核时注入到 LLM。">
                <Textarea value={formPrompt} onChange={(_, d) => setFormPrompt(d.value)} placeholder="例如：检查文档中是否存在XXX问题..." rows={5} />
              </Field>
              <Field label="风险等级" className={classes.formField}>
                <Dropdown value={formRiskLevel} selectedOptions={[formRiskLevel]} onOptionSelect={(_, d) => setFormRiskLevel(d.optionValue as RiskLevel)}>
                  <Option value={RiskLevel.High}>高</Option><Option value={RiskLevel.Medium}>中</Option><Option value={RiskLevel.Low}>低</Option>
                </Dropdown>
              </Field>
              <div className={classes.exampleSection}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600 }}>示例（可选）</span>
                  <Button size="small" appearance="subtle" onClick={addExample}>+ 添加示例</Button>
                </div>
                {formExamples.map((ex, i) => (
                  <div key={i} className={classes.exampleItem}>
                    <div className={classes.exampleInput}>
                      <Input size="small" value={ex.text} onChange={(_, d) => updateExample(i, 'text', d.value)} placeholder="问题文本示例" style={{ marginBottom: '4px' }} />
                      <Input size="small" value={ex.explanation} onChange={(_, d) => updateExample(i, 'explanation', d.value)} placeholder="说明" />
                    </div>
                    <Button size="small" appearance="subtle" icon={<Delete16Regular />} onClick={() => removeExample(i)} />
                  </div>
                ))}
              </div>
            </DialogContent>
            <DialogActions>
              <Button appearance="primary" onClick={handleSave} disabled={saving} icon={saving ? <Spinner size="tiny" /> : undefined}>{editingRule ? '保存' : '创建'}</Button>
              <Button appearance="secondary" onClick={() => setDialogOpen(false)}>取消</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={(_, d) => !d.open && setDeleteDialogOpen(false)}>
        <DialogSurface className={classes.dialogSurface}>
          <DialogBody>
            <DialogTitle>删除规则</DialogTitle>
            <DialogContent><div style={{ padding: '16px', backgroundColor: tokens.colorPaletteRedBackground1, borderRadius: '8px', border: `1px solid ${tokens.colorPaletteRedBorder1}` }}>
              <div style={{ fontSize: '13px', color: tokens.colorPaletteRedForeground1 }}>确定要删除这条规则吗？此操作无法撤销。</div>
            </div></DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setDeleteDialogOpen(false)}>取消</Button>
              <Button appearance="primary" style={{ backgroundColor: tokens.colorPaletteRedBackground3 }} onClick={handleConfirmDelete} disabled={deleting} icon={deleting ? <Spinner size="tiny" /> : <Delete16Regular />}>{deleting ? '删除中...' : '确认删除'}</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </>
  )
}
''')

print("RulesPanel.tsx updated with folder support!")

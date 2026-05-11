"""
fix_default_folder_ui.py
更新 RuleLibrary.tsx — 文件夹卡片加"设为默认/取消默认"按钮
更新 RulesPanel.tsx — 首次打开文档时自动选中默认文件夹的规则
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src")

def write_file(rel_path, content):
    fp = BASE / rel_path
    fp.write_text(content, encoding="utf-8")
    print(f"  WROTE: {rel_path}")

# ========== Only patch the specific parts ==========
import re

# --- RuleLibrary.tsx: add setDefaultFolder import and default button ---
fp = BASE / "pages/ruleLibrary/RuleLibrary.tsx"
text = fp.read_text(encoding="utf-8")

# 1. Add import
text = text.replace(
    "  getFolders, createFolder, updateFolder, deleteFolder as deleteFolderApi,\n} from '../../services/api'",
    "  getFolders, createFolder, updateFolder, deleteFolder as deleteFolderApi, setDefaultFolder,\n} from '../../services/api'",
)

# 2. Add handler function after handleDeleteFolder
text = text.replace(
    "async function handleDeleteFolder(id: string) { try { setError(null); await deleteFolderApi(id); setDeleteFolderTarget(null); await loadRules() } catch (e: any) { setError(e.message) } }",
    "async function handleDeleteFolder(id: string) { try { setError(null); await deleteFolderApi(id); setDeleteFolderTarget(null); await loadRules() } catch (e: any) { setError(e.message) } }\n\n  async function handleSetDefault(folderId: string) { try { setError(null); await setDefaultFolder(folderId); await loadRules() } catch (e: any) { setError(e.message) } }",
)

# 3. Replace folder card actions to add default toggle
text = text.replace(
    """<Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => setDeleteFolderTarget(f)} />""",
    """{f.is_default
                      ? <Button size="small" appearance="subtle" style={{ color: tokens.colorBrandForeground1 }} onClick={() => handleSetDefault(f.id)}>取消默认</Button>
                      : <Button size="small" appearance="subtle" onClick={() => handleSetDefault(f.id)}>设为默认</Button>}
                    <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => setDeleteFolderTarget(f)} />""",
)

# 4. Add "默认" badge after folder name
text = text.replace(
    """<Text weight="semibold" size={400}>{f.name}</Text>
                      {f.description && <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>{f.description}</Text>}""",
    """<Text weight="semibold" size={400}>{f.name}</Text>
                      {f.is_default && <Badge appearance="filled" color="brand" size="small">默认</Badge>}
                      {f.description && <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>{f.description}</Text>}""",
)

fp.write_text(text, encoding="utf-8")
print("  PATCHED: pages/ruleLibrary/RuleLibrary.tsx")

# --- RulesPanel.tsx: auto-select default folder rules on first load ---
fp = BASE / "components/RulesPanel.tsx"
text = fp.read_text(encoding="utf-8")

# 1. Add getDefaultFolder import
text = text.replace(
    "  getFolders,\n} from '../services/api'",
    "  getFolders,\n  getDefaultFolder,\n  setDocumentRule,\n} from '../services/api'",
)

# 2. Replace the loadData function to auto-select default folder
old_loadData = """  async function loadData() {
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
  }"""

new_loadData = """  async function loadData() {
    setLoading(true); setError(undefined)
    try {
      const [allRules, docRules, allFolders] = await Promise.all([getRules(), getDocumentRules(docId), getFolders()])
      const activeRules = allRules.filter(r => r.status === RuleStatus.Active)
      setRules(activeRules); setFolders(allFolders)
      onRulesCountChange?.(activeRules.length)
      let enabledIds = docRules.filter((a: DocumentRuleAssociation) => a.enabled).map((a: DocumentRuleAssociation) => a.rule_id)

      // Auto-select default folder rules if no rules are enabled yet
      if (enabledIds.length === 0 && allFolders.length > 0) {
        const defaultFolder = allFolders.find(f => f.is_default)
        if (defaultFolder) {
          const defaultFolderRuleIds = activeRules.filter(r => r.folder_id === defaultFolder.id).map(r => r.id)
          if (defaultFolderRuleIds.length > 0) {
            for (const rid of defaultFolderRuleIds) { try { await setDocumentRule(docId, rid, true) } catch {} }
            enabledIds = defaultFolderRuleIds
          }
        }
      }
      onEnabledRulesChange(enabledIds)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setLoading(false) }
  }"""

text = text.replace(old_loadData, new_loadData)

# 3. Add "默认" badge in folder row
text = text.replace(
    """<span style={{ flex: 1, fontSize: '12px', fontWeight: 500 }}>{f.name}</span>
                  <Badge appearance="outline" size="small">{fr.length} 条规则</Badge>""",
    """<span style={{ flex: 1, fontSize: '12px', fontWeight: 500 }}>{f.name}</span>
                  {f.is_default && <Badge appearance="filled" color="brand" size="small">默认</Badge>}
                  <Badge appearance="outline" size="small">{fr.length} 条规则</Badge>""",
)

fp.write_text(text, encoding="utf-8")
print("  PATCHED: components/RulesPanel.tsx")

print("\nAll UI patches applied!")

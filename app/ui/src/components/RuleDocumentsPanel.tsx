import { useState, useEffect, useCallback } from 'react'
import { Checkbox, Text, Spinner, makeStyles, tokens } from '@fluentui/react-components'
import { RuleDocumentSource } from '../types/ruleDocument'
import type { RuleDocument, DocumentRuleDocAssociation } from '../types/ruleDocument'
import { getRuleDocuments, getDocumentRuleDocs, setDocumentRuleDoc } from '../services/ruleDocsApi'

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: '8px 14px',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 0',
  },
  docName: {
    fontSize: '13px',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  badge: {
    fontSize: '10px',
    color: tokens.colorNeutralForeground4,
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 0',
    color: tokens.colorNeutralForeground3,
    fontSize: '12px',
  },
  empty: {
    padding: '8px 0',
    color: tokens.colorNeutralForeground4,
    fontSize: '12px',
  },
})

interface RuleDocumentsPanelProps {
  docId: string
  enabledRuleDocIds: string[]
  onEnabledRuleDocIdsChange: (ids: string[]) => void
}

export function RuleDocumentsPanel({
  docId,
  enabledRuleDocIds,
  onEnabledRuleDocIdsChange,
}: RuleDocumentsPanelProps) {
  const classes = useStyles()
  const [documents, setDocuments] = useState<RuleDocument[]>([])
  const [associations, setAssociations] = useState<DocumentRuleDocAssociation[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [docs, assocs] = await Promise.all([
        getRuleDocuments(),
        getDocumentRuleDocs(docId),
      ])
      setDocuments(docs)
      setAssociations(assocs)

      // Initialize enabled IDs from associations
      const enabledIds = assocs
        .filter((a) => a.enabled)
        .map((a) => a.rule_document_id)
      onEnabledRuleDocIdsChange(enabledIds)
    } catch (e) {
      console.error('Failed to load rule documents:', e)
    } finally {
      setLoading(false)
    }
  }, [docId, onEnabledRuleDocIdsChange])

  useEffect(() => { loadData() }, [loadData])

  const handleToggle = async (ruleDocId: string, enabled: boolean) => {
    try {
      await setDocumentRuleDoc(docId, ruleDocId, enabled)
      const newIds = enabled
        ? [...enabledRuleDocIds, ruleDocId]
        : enabledRuleDocIds.filter((id) => id !== ruleDocId)
      onEnabledRuleDocIdsChange(newIds)
    } catch (e) {
      console.error('Failed to toggle rule document:', e)
    }
  }

  if (loading) {
    return (
      <div className={classes.loading}>
        <Spinner size="tiny" /> 加载中...
      </div>
    )
  }

  if (documents.length === 0) {
    return <div className={classes.empty}>暂无规则文档，请在规则库中上传</div>
  }

  return (
    <div className={classes.container}>
      {documents.map((doc) => {
        const enabled = enabledRuleDocIds.includes(doc.id)
        return (
          <div key={doc.id} className={classes.item}>
            <Checkbox
              checked={enabled}
              onChange={(_, data) => handleToggle(doc.id, data.checked as boolean)}
              size="small"
            />
            <Text className={classes.docName} title={doc.name}>
              {doc.name}
            </Text>
            <span className={classes.badge}>
              {doc.source_type === RuleDocumentSource.Parsed ? '已解析' : '上下文'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

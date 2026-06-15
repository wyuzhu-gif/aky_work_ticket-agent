import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Button, Text, Badge, Dialog, DialogSurface, DialogBody, DialogTitle, DialogContent, DialogActions,
  Spinner, makeStyles, tokens, Textarea, MessageBar, MessageBarBody,
} from '@fluentui/react-components'
import {
  ArrowDownloadRegular, DeleteRegular, DocumentRegular, EyeRegular,
  SparkleRegular, CloudArrowUpRegular,
} from '@fluentui/react-icons'
import {
  getRuleDocuments, uploadRuleDocument, deleteRuleDocument as deleteRuleDocApi, getRuleDocumentText, parseRuleDocument,
} from '../../services/ruleDocsApi'
import type { RuleDocument } from '../../types/ruleDocument'
import { RuleDocumentSource } from '../../types/ruleDocument'

const useStyles = makeStyles({
  container: { display: 'flex', flexDirection: 'column', gap: '16px', height: '100%' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' },
  uploadCard: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', padding: '32px 24px', borderRadius: '12px', border: `2px dashed ${tokens.colorNeutralStroke2}`, backgroundColor: tokens.colorNeutralBackground2, cursor: 'pointer', minHeight: '200px', '&:hover': { borderColor: tokens.colorBrandStroke1, backgroundColor: tokens.colorBrandBackground2 } },
  uploadIcon: { fontSize: '48px', color: tokens.colorBrandForeground1 },
  uploadText: { textAlign: 'center', color: tokens.colorNeutralForeground3 },
  acceptedFormats: { fontSize: '12px', color: tokens.colorNeutralForeground4 },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', padding: '60px 20px', color: tokens.colorNeutralForeground3 },
  docCard: { display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', borderRadius: '12px', border: `1px solid ${tokens.colorNeutralStroke2}`, backgroundColor: tokens.colorNeutralBackground1, '&:hover': { borderColor: tokens.colorBrandStroke1, boxShadow: tokens.shadow2 } },
})

function FileTypeIcon({ fileType }: { fileType: string }) {
  const c: Record<string, string> = { pdf: '#E74C3C', docx: '#2980B9', md: '#27AE60', txt: '#7F8C8D' }
  return <DocumentRegular style={{ color: c[fileType] || tokens.colorBrandForeground1 }} />
}
function SourceBadge({ sourceType }: { sourceType: string }) {
  return sourceType === RuleDocumentSource.Parsed
    ? <Badge appearance="filled" color="success" size="small">已解析</Badge>
    : <Badge appearance="outline" color="informative" size="small">上下文注入</Badge>
}

export default function RuleDocManage() {
  const classes = useStyles()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Docs state
  const [documents, setDocuments] = useState<RuleDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [parsingId, setParsingId] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState<{ name: string; text: string } | null>(null)
  const [deleteDocTarget, setDeleteDocTarget] = useState<RuleDocument | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadDocs = useCallback(async () => { try { setLoadingDocs(true); setDocuments(await getRuleDocuments()) } catch (e: any) { setError(e.message) } finally { setLoadingDocs(false) } }, [])
  useEffect(() => { loadDocs() }, [loadDocs])

  // Handlers
  const handleUpload = async (file: File) => { try { setUploading(true); setError(null); await uploadRuleDocument(file); await loadDocs() } catch (e: any) { setError(e.message) } finally { setUploading(false) } }
  const handleParse = async (id: string) => { try { setParsingId(id); setError(null); await parseRuleDocument(id); await loadDocs() } catch (e: any) { setError(e.message) } finally { setParsingId(null) } }
  const handleViewText = async (id: string, name: string) => { try { const r = await getRuleDocumentText(id); setPreviewText({ name, text: r.extracted_text }) } catch (e: any) { setError(e.message) } }
  const handleDeleteDoc = async (id: string) => { try { setError(null); await deleteRuleDocApi(id); setDeleteDocTarget(null); await loadDocs() } catch (e: any) { setError(e.message) } }

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer.files?.[0]; if (f) handleUpload(f) }
  const handleDownloadTemplate = () => { const o = import.meta.env.VITE_API_ORIGIN ?? ''; window.open(`${o}/api/v1/rule-documents-template`, '_blank') }

  return (
    <div className={classes.container}>
      <Text size={500} weight="semibold">规则文档管理</Text>
      {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}

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

      {/* Delete Doc Dialog */}
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

      {/* Doc Text Preview Dialog */}
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

import { useState } from 'react'
import { tokens } from '@fluentui/react-components'
import { ChevronUpRegular, ChevronDownRegular, BookRegular } from '@fluentui/react-icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { WikiRef } from './types'

interface KnowledgeReferenceProps {
  results: WikiRef[]
}

/** 知识引用折叠面板 */
export function KnowledgeReference({ results }: KnowledgeReferenceProps) {
  const [expanded, setExpanded] = useState(false)

  if (!results.length) return null

  return (
    <div style={{ marginTop: '8px', border: `1px solid ${tokens.colorNeutralStroke2}`, borderRadius: '8px', backgroundColor: tokens.colorNeutralBackground3 }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px', cursor: 'pointer', fontSize: '12px', fontWeight: 600, color: tokens.colorBrandForeground1, borderBottom: expanded ? `1px solid ${tokens.colorNeutralStroke3}` : 'none' }}
      >
        {expanded ? <ChevronUpRegular style={{ fontSize: 14 }} /> : <ChevronDownRegular style={{ fontSize: 14 }} />}
        <BookRegular style={{ fontSize: 14 }} />
        <span>安全知识引用（{results.length}条）</span>
      </div>
      {expanded && (
        <div style={{ maxHeight: '50vh', overflowY: 'auto', padding: '8px 12px' }}>
          {results.map((ref, idx) => (
            <div key={idx} style={{ marginBottom: '8px', paddingBottom: idx < results.length - 1 ? '8px' : 0, borderBottom: idx < results.length - 1 ? `1px solid ${tokens.colorNeutralStroke3}` : 'none' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '4px', color: tokens.colorNeutralForeground1 }}>{ref.title || ref.filepath}</div>
              {ref.content ? (
                <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.85, whiteSpace: 'pre-wrap' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{ref.content}</ReactMarkdown>
                </div>
              ) : (
                <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.85 }}>{ref.snippet || ''}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

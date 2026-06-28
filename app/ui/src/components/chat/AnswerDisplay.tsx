import { Text, tokens } from '@fluentui/react-components'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStyles } from './useChatStyles'

interface AnswerDisplayProps {
  content: string
  title?: string
}

/**
 * AI 答案渲染 - 渲染 markdown 报告
 * 复用自 SmartQuery.tsx, 智能问数 + hermes 问答共用
 */
export function AnswerDisplay({ content, title = '数据分析报告' }: AnswerDisplayProps) {
  const classes = useChatStyles()
  if (!content.trim()) return null

  // 压缩空行: 把 3+ 个连续 \n 压缩成 1 个 \n\n, 把段内 \n\n 变成 \n
  const compact = content
    .replace(/\n{3,}/g, '\n\n')
    .replace(/(\n- [^\n]+)\n\n(?=- )/g, '$1\n')

  return (
    <div className={classes.answerWrap}>
      <div className={classes.answerTitle}>{title}</div>
      <div style={{ fontSize: 15, lineHeight: 1.5 }}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => <h1 style={{ fontSize: 19, fontWeight: 700, color: tokens.colorBrandForeground1, marginTop: 8, marginBottom: 4 }}>{children}</h1>,
            h2: ({ children }) => <h2 style={{ fontSize: 17, fontWeight: 600, color: tokens.colorBrandForeground1, marginTop: 6, marginBottom: 2 }}>{children}</h2>,
            h3: ({ children }) => <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 4, marginBottom: 1 }}>{children}</h3>,
            p: ({ children }) => <p style={{ fontSize: 15, lineHeight: 1.5, marginTop: 0, marginBottom: 2 }}>{children}</p>,
            ul: ({ children }) => <ul style={{ fontSize: 15, marginLeft: 16, marginTop: 0, marginBottom: 2, listStyleType: 'disc', paddingLeft: 0 }}>{children}</ul>,
            ol: ({ children }) => <ol style={{ fontSize: 15, marginLeft: 16, marginTop: 0, marginBottom: 2, paddingLeft: 0 }}>{children}</ol>,
            li: ({ children }) => <li style={{ marginBottom: 1, lineHeight: 1.45 }}>{children}</li>,
            strong: ({ children }) => <strong style={{ color: tokens.colorBrandForeground1, fontWeight: 600 }}>{children}</strong>,
            code: ({ children, className }: any) => {
              const inline = !className
              return inline
                ? <code style={{ backgroundColor: tokens.colorNeutralBackground3, padding: '1px 4px', borderRadius: 3, fontSize: 14 }}>{children}</code>
                : <code style={{ display: 'block', backgroundColor: tokens.colorNeutralBackground3, padding: 8, borderRadius: 4, fontSize: 14, overflowX: 'auto', margin: '8px 0' }}>{children}</code>
            },
            br: () => <br style={{ lineHeight: 0.3 }} />,
            hr: () => <hr style={{ margin: '4px 0', border: 'none', borderTop: `1px solid ${tokens.colorNeutralStroke3}` }} />,
          }}
        >
          {compact}
        </ReactMarkdown>
      </div>
    </div>
  )
}

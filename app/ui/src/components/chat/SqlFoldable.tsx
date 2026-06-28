import { useState } from 'react'
import { Button, tokens } from '@fluentui/react-components'
import { ChevronUpRegular, ChevronDownRegular } from '@fluentui/react-icons'

interface SqlFoldableProps {
  sql: string
}

/** SQL 折叠组件 - 默认隐藏, 业务用户不需要看 SQL */
export function SqlFoldable({ sql }: SqlFoldableProps) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ marginTop: '8px' }}>
      <Button
        appearance="subtle"
        size="small"
        icon={expanded ? <ChevronUpRegular style={{ fontSize: 12 }} /> : <ChevronDownRegular style={{ fontSize: 12 }} />}
        onClick={() => setExpanded(!expanded)}
        style={{ fontSize: '11px' }}
      >
        {expanded ? '收起' : '查看'} SQL 语句（{sql.length} 字符）
      </Button>
      {expanded && (
        <pre style={{
          marginTop: '4px',
          padding: '8px',
          backgroundColor: tokens.colorNeutralBackground3,
          borderRadius: '4px',
          fontSize: '11px',
          overflowX: 'auto',
          fontFamily: 'monospace',
          color: tokens.colorNeutralForeground2,
        }}>
          {sql}
        </pre>
      )}
    </div>
  )
}

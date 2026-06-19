import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Input,
  makeStyles,
  MessageBar,
  MessageBarBody,
  Spinner,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Text,
  tokens,
  Divider,
  Badge,
  Tooltip,
} from '@fluentui/react-components'
import {
  SendRegular,
  DataUsageRegular,
  ArrowUndoRegular,
  AddRegular,
  DeleteRegular,
  ChatRegular,
  NavigationRegular,
  BookRegular,
  ChevronDownRegular,
  ChevronUpRegular,
} from '@fluentui/react-icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Chart as ChartJS, CategoryScale, LinearScale, TimeScale, BarElement, LineElement, PointElement, ArcElement, Title, Tooltip as ChartTooltip, Legend } from 'chart.js'
import { Bar, Line, Pie, Scatter } from 'react-chartjs-2'
import 'chartjs-adapter-date-fns'  // TimeScale 需要日期适配器
import ChartDataLabels from 'chartjs-plugin-datalabels'
import {
  listSessions,
  createSession,
  getSession,
  deleteSession,
  type SessionInfo,
  type SessionMessage,
} from '../../services/sessionApi'

ChartJS.register(CategoryScale, LinearScale, TimeScale, BarElement, LineElement, PointElement, ArcElement, Title, ChartTooltip, Legend, ChartDataLabels)

interface ThinkingStep {
  action: string
  tool_name: string
  status: 'preparing' | 'running' | 'completed'
  duration_ms?: number
  result?: string
  update?: boolean
}

interface QueryData {
  columns: string[]
  data: Record<string, unknown>[]
  sql: string
}

/** 知识引用：每个页面返回 filepath/title/snippet/content */
interface WikiRef {
  filepath: string
  title: string
  snippet: string
  content?: string     // 展开时加载全文
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  thinkingSteps?: ThinkingStep[]
  queryData?: QueryData
  chartConfig?: Record<string, unknown>
  wikiResults?: WikiRef[]
}

const useStyles = makeStyles({
  root: {
    display: 'flex',
    height: 'calc(100vh - 96px)',
    gap: '0',
  },
  sidebar: {
    width: '260px',
    minWidth: '260px',
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: tokens.colorNeutralBackground2,
    overflow: 'hidden',
  },
  sidebarHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 12px 8px',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  sidebarList: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 0',
  },
  sessionItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 12px',
    cursor: 'pointer',
    borderLeft: '3px solid transparent',
    transition: 'background 0.15s, border-color 0.15s',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  sessionItemActive: {
    backgroundColor: tokens.colorBrandBackground2,
    borderLeftColor: tokens.colorBrandStroke1,
  },
  sessionTitle: {
    flex: 1,
    fontSize: '13px',
    lineHeight: '20px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: tokens.colorNeutralForeground1,
  },
  sessionTime: {
    fontSize: '10px',
    color: tokens.colorNeutralForeground3,
    marginTop: '2px',
  },
  sessionDelete: {
    opacity: 0,
    transition: 'opacity 0.15s',
    minWidth: '24px',
    padding: '0',
  },
  sessionItemHover: {
    [`&:hover .sessionDelete`]: {
      opacity: 1,
    },
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '8px',
    padding: '0 4px',
  },
  title: { fontSize: '20px', fontWeight: 700, color: tokens.colorBrandForeground1 },
  messagesArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 0',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  msgBubble: {
    maxWidth: '85%',
    padding: '12px 16px',
    borderRadius: '12px',
    fontSize: '14px',
    lineHeight: '22px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
    border: `1px solid ${tokens.colorBrandStroke2}`,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: tokens.colorNeutralBackground1,
    color: tokens.colorNeutralForeground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  stepsWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    marginBottom: '8px',
    padding: '8px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  dataSection: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
    overflowX: 'auto',
  },
  sqlTag: {
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
    marginTop: '4px',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap',
    maxHeight: '80px',
    overflowY: 'auto',
  },
  inputArea: {
    display: 'flex',
    gap: '8px',
    paddingTop: '8px',
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  inputField: { flex: 1 },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    color: tokens.colorNeutralForeground3,
  },
  emptyIcon: { fontSize: '48px', opacity: 0.5 },
  chartWrap: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  answerWrap: {
    marginTop: '8px',
    padding: '12px',
    borderRadius: '8px',
    border: `1px solid ${tokens.colorBrandStroke2}`,
    backgroundColor: tokens.colorNeutralBackground1,
  },
  answerTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: tokens.colorBrandForeground1,
    marginBottom: '8px',
    paddingBottom: '4px',
    borderBottom: `1px solid ${tokens.colorNeutralStroke3}`,
  },
})

function StepIndicator({ step }: { step: ThinkingStep }) {
  const done = step.status === 'completed'
  const running = step.status === 'running'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
      {done ? '✓' : running ? '●' : '○'} {step.action}
      {step.duration_ms != null && <span style={{ opacity: 0.6 }}>({step.duration_ms}ms)</span>}
    </div>
  )
}

function DataTable({ data }: { data: QueryData }) {
  if (!data.columns.length || !data.data.length) return null
  return (
    <Table size="small" style={{ fontSize: 12 }}>
      <TableHeader>
        <TableRow>
          {data.columns.map(c => <TableHeaderCell key={c}>{c}</TableHeaderCell>)}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.data.slice(0, 50).map((row, i) => (
          <TableRow key={i}>
            {data.columns.map(c => (
              <TableCell key={c}>{String(row[c] ?? '')}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function ChartDisplay({ config }: { config: Record<string, unknown> }) {
  const classes = useStyles()
  const { type, data, options } = config as { type: string; data: any; options: any }

  if (!type || !data) return null

  const chartProps = {
    data,
    options: { ...options, maintainAspectRatio: false },
  }

  const renderChart = () => {
    switch (type) {
      case 'bar': return <Bar {...chartProps} />
      case 'line': return <Line {...chartProps} />
      case 'pie': return <Pie {...chartProps} />
      case 'scatter': return <Scatter {...chartProps} />
      default: return null
    }
  }

  return (
    <div className={classes.chartWrap}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <DataUsageRegular style={{ fontSize: 14 }} />
        <Text size={200} weight="semibold">数据可视化</Text>
      </div>
      <div style={{ height: 300, position: 'relative' }}>
        {renderChart()}
      </div>
    </div>
  )
}

function AnswerDisplay({ content }: { content: string }) {
  const classes = useStyles()
  if (!content.trim()) return null
  return (
    <div className={classes.answerWrap}>
      <div className={classes.answerTitle}>数据分析报告</div>
      <div style={{ fontSize: 13, lineHeight: 1.6 }}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h2: ({ children }) => <h2 style={{ fontSize: 14, fontWeight: 600, color: tokens.colorBrandForeground1, marginTop: 8, marginBottom: 4 }}>{children}</h2>,
            h3: ({ children }) => <h3 style={{ fontSize: 13, fontWeight: 600, marginTop: 6, marginBottom: 2 }}>{children}</h3>,
            p: ({ children }) => <p style={{ fontSize: 13, lineHeight: 1.5, marginTop: 0, marginBottom: 4 }}>{children}</p>,
            ul: ({ children }) => <ul style={{ fontSize: 13, marginLeft: 16, marginTop: 0, marginBottom: 4, listStyleType: 'disc', paddingLeft: 0 }}>{children}</ul>,
            ol: ({ children }) => <ol style={{ fontSize: 13, marginLeft: 16, marginTop: 0, marginBottom: 4, paddingLeft: 0 }}>{children}</ol>,
            li: ({ children }) => <li style={{ marginBottom: 2, lineHeight: 1.5 }}>{children}</li>,
            strong: ({ children }) => <strong style={{ color: tokens.colorBrandForeground1, fontWeight: 600 }}>{children}</strong>,
            code: ({ children, className }) => {
              const inline = !className
              return inline
                ? <code style={{ backgroundColor: tokens.colorNeutralBackground3, padding: '1px 4px', borderRadius: 3, fontSize: 12 }}>{children}</code>
                : <code style={{ display: 'block', backgroundColor: tokens.colorNeutralBackground3, padding: 8, borderRadius: 4, fontSize: 12, overflowX: 'auto', margin: '8px 0' }}>{children}</code>
            },
            br: () => <br style={{ lineHeight: 0.5 }} />,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/** 知识引用折叠面板组件 */
function KnowledgeReference({ results }: { results: WikiRef[] }) {
  const [expanded, setExpanded] = useState(false)
  const classes = useStyles()

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

/** 把后端 SessionMessage 转为前端 ChatMessage */
function sessionMessageToChat(sm: SessionMessage): ChatMessage {
  return {
    role: sm.role,
    content: sm.content,
    isStreaming: false,
    thinkingSteps: sm.thinkingSteps ?? undefined,
    queryData: sm.queryData ?? undefined,
    chartConfig: sm.chartConfig ?? undefined,
  }
}

/** 格式化时间 */
function fmtTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso.replace(' ', 'T'))
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin}分钟前`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `${diffH}小时前`
    const diffD = Math.floor(diffH / 24)
    if (diffD < 7) return `${diffD}天前`
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch { return '' }
}

export default function SmartQuery() {
  const classes = useStyles()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 会话列表状态
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [])

  // 追踪最后一条用户问题，用于 wiki 检索
  const lastQuery = useRef<string>('')

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch (e) {
      console.error('Failed to load sessions:', e)
    }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  // 切换到某个会话，加载历史消息
  const switchSession = useCallback(async (sessionId: string) => {
    try {
      const data = await getSession(sessionId)
      const chatMsgs = data.messages.map(sessionMessageToChat)
      setMessages(chatMsgs)
      setActiveSessionId(sessionId)
      scrollToBottom()
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }, [scrollToBottom])

  // 新建会话
  const handleNewSession = useCallback(async () => {
    try {
      const session = await createSession()
      setActiveSessionId(session.id)
      setMessages([])
      setError(null)
      loadSessions()
    } catch (e) {
      console.error('Failed to create session:', e)
    }
  }, [loadSessions])

  // 删除会话
  const handleDeleteSession = useCallback(async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    try {
      await deleteSession(sessionId)
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
        setMessages([])
      }
      loadSessions()
    } catch (e2) {
      console.error('Failed to delete session:', e2)
    }
  }, [activeSessionId, loadSessions])

  // 发送消息
  const handleSend = useCallback(async () => {
    const q = input.trim()
    if (!q || streaming) return
    lastQuery.current = q  // 记录用户问题，供 wiki 检索使用
    setInput('')
    setError(null)
    setStreaming(true)

    // 如果没有活动会话，先创建
    let sid = activeSessionId
    if (!sid) {
      try {
        const session = await createSession(q.slice(0, 50))
        sid = session.id
        setActiveSessionId(sid)
        loadSessions()
      } catch {
        setStreaming(false)
        return
      }
    }

    const userMsg: ChatMessage = { role: 'user', content: q }
    const aiMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      isStreaming: true,
      thinkingSteps: [],
    }
    setMessages(prev => [...prev, userMsg, aiMsg])

    try {
      const resp = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, session_id: sid }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('No response body')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue

          let ev: Record<string, unknown>
          try {
            ev = JSON.parse(trimmed.slice(6))
          } catch { continue }

          setMessages(prev => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last.role !== 'assistant') return prev

            const updated = { ...last }
            switch (ev.type) {
              case 'step': {
                const steps = [...(updated.thinkingSteps || [])]
                const stepEv = ev as unknown as ThinkingStep
                if (stepEv.update) {
                  const idx = steps.findLastIndex
                    ? steps.findLastIndex(s => s.tool_name === stepEv.tool_name)
                    : (() => { for (let i = steps.length - 1; i >= 0; i--) { if (steps[i].tool_name === stepEv.tool_name) return i } return -1 })()
                  if (idx >= 0) steps[idx] = stepEv
                  else steps.push(stepEv)
                } else {
                  steps.push(stepEv)
                }
                updated.thinkingSteps = steps
                break
              }
              case 'data':
                updated.queryData = {
                  columns: (ev.columns as string[]) || [],
                  data: (ev.data as Record<string, unknown>[]) || [],
                  sql: (ev.sql as string) || '',
                }
                break
              case 'chart_config':
                updated.chartConfig = (ev.config as Record<string, unknown>) || (ev as Record<string, unknown>)
                break
              case 'answer':
                updated.content += (ev.content as string) || ''
                break
              case 'done':
                updated.isStreaming = false
                break
              case 'error':
                updated.content += `\n[错误] ${(ev as { message: string }).message}`
                updated.isStreaming = false
                break
            }
            next[next.length - 1] = updated
            return next
          })
        }
        scrollToBottom()
      }

      // Handle any remaining buffer
      if (buffer.trim().startsWith('data: ')) {
        try {
          const ev = JSON.parse(buffer.trim().slice(6))
          setMessages(prev => {
            const next = [...prev]
            const last = { ...next[next.length - 1] }
            if (ev.type === 'done') last.isStreaming = false
            else if (ev.type === 'error') { last.content += `\n[错误] ${ev.message}`; last.isStreaming = false }
            next[next.length - 1] = last
            return next
          })
        } catch { /* ignore */ }
      }

      // streaming 完成，自动查询知识引用
      const query = lastQuery.current
      if (query) {
        try {
          const res = await fetch(`/api/wiki?q=${encodeURIComponent(query)}`)
          const json = await res.json()
          if (json.results?.length > 0) {
            setMessages(prev => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last.role === 'assistant') {
                last.wikiResults = json.results as WikiRef[]
                next[next.length - 1] = last
              }
              return next
            })
          }
        } catch (eWiki) {
          console.warn('Wiki reference fetch failed:', eWiki)
        }
      }

      // 刷新会话列表（标题可能已更新）
      loadSessions()
    } catch (e: any) {
      setError(e.message || '请求失败')
      setMessages(prev => {
        const next = [...prev]
        const last = { ...next[next.length - 1] }
        last.isStreaming = false
        last.content = '请求失败，请重试'
        next[next.length - 1] = last
        return next
      })
    } finally {
      setStreaming(false)
      inputRef.current?.focus()
    }
  }, [input, streaming, activeSessionId, scrollToBottom, loadSessions])

  const handleClear = useCallback(() => {
    setMessages([])
    setActiveSessionId(null)
    setError(null)
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  return (
    <div className={classes.root}>
      {/* 左侧会话列表 */}
      {!sidebarCollapsed && (
        <div className={classes.sidebar}>
          <div className={classes.sidebarHeader}>
            <Text size={300} weight="semibold">历史对话</Text>
            <Tooltip content="新建对话" relationship="label">
              <Button appearance="subtle" size="small" icon={<AddRegular />} onClick={handleNewSession} />
            </Tooltip>
          </div>
          <div className={classes.sidebarList}>
            {sessions.length === 0 && (
              <div style={{ padding: '20px 12px', textAlign: 'center', color: tokens.colorNeutralForeground3, fontSize: 12 }}>
                暂无历史对话
              </div>
            )}
            {sessions.map(s => (
              <div
                key={s.id}
                className={`${classes.sessionItem} ${s.id === activeSessionId ? classes.sessionItemActive : ''}`}
                onClick={() => switchSession(s.id)}
                style={s.id === activeSessionId ? { backgroundColor: tokens.colorBrandBackground2, borderLeftColor: tokens.colorBrandStroke1 } : {}}
              >
                <ChatRegular style={{ fontSize: 16, flexShrink: 0, color: tokens.colorNeutralForeground3 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className={classes.sessionTitle}>{s.title || '未命名对话'}</div>
                  <div className={classes.sessionTime}>{fmtTime(s.updated_at || s.created_at)}</div>
                </div>
                <Button
                  className={classes.sessionDelete}
                  appearance="subtle"
                  size="small"
                  icon={<DeleteRegular />}
                  title="删除会话"
                  onClick={(e) => handleDeleteSession(e, s.id)}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 主聊天区域 */}
      <div className={classes.main}>
        <div className={classes.header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tooltip content={sidebarCollapsed ? '展开侧栏' : '收起侧栏'} relationship="label">
              <Button appearance="subtle" size="small" icon={<NavigationRegular />} onClick={() => setSidebarCollapsed(c => !c)} />
            </Tooltip>
            <DataUsageRegular style={{ fontSize: 20 }} />
            <Text className={classes.title}>智能问数</Text>
            <Badge appearance="ghost" color="informative" size="small">NL2SQL</Badge>
          </div>
          {messages.length > 0 && (
            <Button appearance="subtle" size="small" icon={<ArrowUndoRegular />} onClick={handleClear}>
              清空对话
            </Button>
          )}
        </div>

        {error && (
          <MessageBar intent="error">
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        )}

        {messages.length === 0 ? (
          <div className={classes.empty}>
            <DataUsageRegular className={classes.emptyIcon} />
            <Text size={400} weight="semibold">智能数据问答</Text>
            <Text size={200} style={{ maxWidth: 400, textAlign: 'center' }}>
              用自然语言提问，AI 会自动转换为 SQL 查询数据库并返回结果。
              <br />例如：「各区域动火作业数量统计」「本月作业票完成情况」
            </Text>
          </div>
        ) : (
          <div className={classes.messagesArea}>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`${classes.msgBubble} ${msg.role === 'user' ? classes.userBubble : classes.aiBubble}`}
              >
                {msg.role === 'user' && <div>{msg.content}</div>}
                {msg.role === 'assistant' && msg.isStreaming && !msg.content && (!msg.thinkingSteps?.length) && !msg.queryData && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Spinner size="tiny" /> 思考中...
                  </div>
                )}

                {msg.role === 'assistant' && msg.thinkingSteps && msg.thinkingSteps.length > 0 && (
                  <div className={classes.stepsWrap}>
                    <Text size={200} weight="semibold" style={{ marginBottom: 4 }}>推理步骤</Text>
                    {msg.thinkingSteps.map((s, j) => <StepIndicator key={j} step={s} />)}
                  </div>
                )}

                {msg.role === 'assistant' && msg.queryData && (
                  <div className={classes.dataSection}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <Text size={200} weight="semibold">查询结果</Text>
                      <Text size={100} style={{ color: tokens.colorNeutralForeground3 }}>({msg.queryData.data.length} 行)</Text>
                    </div>
                    <Divider style={{ margin: '4px 0' }} />
                    <DataTable data={msg.queryData} />
                    {msg.queryData.sql && (
                      <div className={classes.sqlTag}>
                        SQL: {msg.queryData.sql}
                      </div>
                    )}
                  </div>
                )}

                {msg.role === 'assistant' && msg.chartConfig && <ChartDisplay config={msg.chartConfig} />}

                {msg.role === 'assistant' && msg.content && (
                  <AnswerDisplay content={msg.content} />
                )}

                {/* knowledge refs: 仅在非 streaming、有结果时展示 */}
                {msg.role === 'assistant' && !msg.isStreaming && msg.wikiResults && msg.wikiResults.length > 0 && (
                  <KnowledgeReference results={msg.wikiResults} />
                )}

                {msg.role === 'assistant' && msg.isStreaming && !msg.content && !msg.queryData && !msg.chartConfig && msg.thinkingSteps && msg.thinkingSteps.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                    <Spinner size="tiny" /> 等待响应...
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        <div className={classes.inputArea}>
          <Input
            ref={inputRef}
            className={classes.inputField}
            placeholder="输入问题，例如：各区域动火作业数量..."
            value={input}
            onChange={(_, d) => setInput(d.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
          />
          <Button
            appearance="primary"
            icon={<SendRegular />}
            disabled={streaming || !input.trim()}
            onClick={handleSend}
          >
            {streaming ? '查询中...' : '发送'}
          </Button>
        </div>
      </div>
    </div>
  )
}

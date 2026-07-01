import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Input,
  Spinner,
  Text,
  MessageBar,
  MessageBarBody,
  Tooltip,
} from '@fluentui/react-components'
import {
  SendRegular,
  ChatRegular,
  StopRegular,
  AddRegular,
  DeleteRegular,
  HistoryRegular,
} from '@fluentui/react-icons'
import {
  useChatStyles,
  AnswerDisplay,
  ChartDisplay,
  fmtTime,
  type ChatMessage,
} from '../../components/chat'
import { agentChatStream, agentCancel, type AgentChatHandle } from '../../services/agentChatApi'
import {
  listSessions,
  createSession,
  getSession,
  deleteSession,
  type SessionInfo,
  type SessionMessage,
} from '../../services/sessionApi'

interface UiMessage extends ChatMessage {
  timestamp: string
  chartConfig?: Record<string, unknown>
}

/** SessionMessage → UiMessage 转换 */
function sessionMsgToUi(msg: SessionMessage): UiMessage {
  return {
    role: msg.role,
    content: msg.content || '',
    timestamp: (msg.created_at || '').replace('T', ' ').slice(0, 19),
    chartConfig: msg.chartConfig ?? undefined,
  }
}

/** 按日期分组会话 */
function groupSessionsByDate(sessions: SessionInfo[]): { label: string; items: SessionInfo[] }[] {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const groups: Record<string, SessionInfo[]> = { 今天: [], 昨天: [], 更早: [] }
  for (const s of sessions) {
    const d = new Date(s.updated_at || s.created_at)
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
    if (day.getTime() === today.getTime()) groups['今天'].push(s)
    else if (day.getTime() === yesterday.getTime()) groups['昨天'].push(s)
    else groups['更早'].push(s)
  }
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }))
}

export default function HermesChat() {
  const classes = useChatStyles()
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const currentHandleRef = useRef<AgentChatHandle | null>(null)

  // 会话历史状态
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessions(50, 0, 'hermes_chat')
      setSessions(list)
    } catch {
      // 静默失败, 不影响主功能
    }
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  // 切换会话
  const switchSession = useCallback(async (sessionId: string) => {
    if (loading) return
    try {
      const data = await getSession(sessionId)
      const uiMsgs = (data.messages || []).map(sessionMsgToUi)
      setMessages(uiMsgs)
      setCurrentSessionId(sessionId)
      setError(null)
    } catch {
      setError('加载会话历史失败')
    }
  }, [loading])

  // 新建聊天
  const newChat = useCallback(() => {
    if (loading) return
    setMessages([])
    setCurrentSessionId('')
    setError(null)
    setTimeout(() => inputRef.current?.focus(), 100)
  }, [loading])

  // 删除会话
  const handleDeleteSession = useCallback(async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    try {
      await deleteSession(sessionId)
      // 如果删的是当前会话, 清空聊天区
      if (sessionId === currentSessionId) {
        setMessages([])
        setCurrentSessionId('')
      }
      await loadSessions()
    } catch {
      setError('删除会话失败')
    }
  }, [currentSessionId, loadSessions])

  const handleStop = useCallback(async () => {
    const h = currentHandleRef.current
    if (!h) return
    h.abort()
    if (h.taskId) {
      await agentCancel({ taskId: h.taskId, traceId: h.traceId })
    } else if (h.traceId) {
      await agentCancel({ traceId: h.traceId })
    }
    currentHandleRef.current = null
    setLoading(false)
  }, [])

  const handleSend = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg: UiMessage = {
      role: 'user',
      content: q,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
    }
    const aiMsgIdx: number = messages.length + 1
    setMessages(prev => [...prev, userMsg, {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      isStreaming: true,
    } as UiMessage])
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const handle = await agentChatStream(
        {
          question: q,
          ...(currentSessionId ? { sessionId: currentSessionId } : {}),
        },
        {
          onMetadata: (meta) => {
            // 后端创建/确认了会话, 保存 session_id
            if (meta.sessionId && meta.sessionId !== currentSessionId) {
              setCurrentSessionId(meta.sessionId)
            }
          },
          onDelta: (delta) => {
            if (typeof delta.content === 'string' && delta.content.length > 0) {
              setMessages(prev => prev.map((m, i) =>
                i === aiMsgIdx
                  ? { ...m, content: m.content + delta.content }
                  : m
              ))
            }
          },
          onChart: (chartConfig, cleanedText) => {
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx
                ? { ...m, chartConfig, content: cleanedText || m.content }
                : m
            ))
          },
          onResponse: (respPayload) => {
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx
                ? {
                    ...m,
                    content: respPayload.answer || m.content,
                    chartConfig: respPayload.chart_config ?? m.chartConfig,
                    isStreaming: false,
                  }
                : m
            ))
            setLoading(false)
            currentHandleRef.current = null
            setTimeout(() => inputRef.current?.focus(), 100)
            if (respPayload.partial) {
              setError(`⚠️ 响应被截断 (type=${respPayload.type}, trace=${respPayload.trace_id || '?'})`)
            }
          },
          onDone: () => {
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx && m.isStreaming
                ? { ...m, isStreaming: false }
                : m
            ))
            setLoading(false)
            currentHandleRef.current = null
            // 刷新会话列表 (updated_at 变了)
            loadSessions()
            setTimeout(() => inputRef.current?.focus(), 100)
          },
          onError: (err) => {
            setError(err.message || '调用失败')
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx
                ? { ...m, isStreaming: false, content: m.content || '(生成被取消)' }
                : m
            ))
            setLoading(false)
            currentHandleRef.current = null
          },
        },
      )
      currentHandleRef.current = handle
    } catch (e: any) {
      setError(e.message || '调用失败')
      setLoading(false)
      currentHandleRef.current = null
    }
  }, [input, loading, messages.length, currentSessionId, loadSessions])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const groupedSessions = groupSessionsByDate(sessions)

  return (
    <div className={classes.root}>
      {/* 左侧侧边栏 */}
      {!sidebarCollapsed && (
        <div className={classes.sidebar}>
          <div className={classes.sidebarHeader}>
            <Text style={{ fontSize: '14px', fontWeight: 600 }}>
              <HistoryRegular style={{ marginRight: '6px' }} />
              历史记录
            </Text>
            <div style={{ display: 'flex', gap: '4px' }}>
              <Tooltip content="新建聊天" relationship="label">
                <Button
                  appearance="subtle"
                  size="small"
                  icon={<AddRegular />}
                  onClick={newChat}
                  disabled={loading}
                />
              </Tooltip>
              <Tooltip content="收起侧边栏" relationship="label">
                <Button
                  appearance="subtle"
                  size="small"
                  icon={<span style={{ fontSize: '12px' }}>◀</span>}
                  onClick={() => setSidebarCollapsed(true)}
                />
              </Tooltip>
            </div>
          </div>

          <div className={classes.sidebarList}>
            {groupedSessions.length === 0 && (
              <Text size={200} style={{ display: 'block', padding: '16px 12px', color: '#888' }}>
                暂无历史记录
              </Text>
            )}
            {groupedSessions.map(group => (
              <div key={group.label}>
                <Text
                  size={100}
                  style={{
                    display: 'block',
                    padding: '8px 12px 4px',
                    color: '#888',
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  {group.label}
                </Text>
                {group.items.map(s => (
                  <div
                    key={s.id}
                    className={`${classes.sessionItem} ${classes.sessionItemHover} ${s.id === currentSessionId ? classes.sessionItemActive : ''}`}
                    onClick={() => switchSession(s.id)}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className={classes.sessionTitle}>{s.title || '(无标题)'}</div>
                      <div className={classes.sessionTime}>
                        {(s.updated_at || '').slice(5, 16).replace('T', ' ')}
                      </div>
                    </div>
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<DeleteRegular />}
                      style={{ opacity: 0.5, minWidth: '24px', padding: '0' }}
                      onClick={(e) => handleDeleteSession(e, s.id)}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 展开侧边栏按钮 (收起时显示) */}
      {sidebarCollapsed && (
        <div
          style={{
            width: '32px',
            minWidth: '32px',
            borderRight: '1px solid #e0e0e0',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingTop: '12px',
            backgroundColor: '#fafafa',
          }}
        >
          <Tooltip content="展开侧边栏" relationship="label">
            <Button
              appearance="subtle"
              size="small"
              icon={<span style={{ fontSize: '12px' }}>▶</span>}
              onClick={() => setSidebarCollapsed(false)}
            />
          </Tooltip>
        </div>
      )}

      {/* 右侧主聊天区 */}
      <div className={classes.main} style={{ padding: '0 16px' }}>
        <div className={classes.header}>
          <Text className={classes.title}>智能问答</Text>
          <Text size={200} style={{ color: '#666' }}>
            数据查询 + 安全规范
          </Text>
        </div>

        <div className={classes.messagesArea}>
          {messages.length === 0 && (
            <div className={classes.empty}>
              <ChatRegular className={classes.emptyIcon} />
              <Text size={200} style={{ opacity: 0.6 }}>
                例: "上周动火作业数量"、"动火作业需要哪些审批"
              </Text>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ width: '100%', alignSelf: 'stretch', minWidth: 0 }}>
              {msg.role === 'user' ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                  <div className={`${classes.msgBubble} ${classes.userBubble}`}>
                    {msg.content}
                  </div>
                  <Text size={100} style={{ color: '#888', fontSize: 10 }}>
                    {fmtTime(msg.timestamp)}
                  </Text>
                </div>
              ) : (
                <div style={{
                  width: '80%',
                  minWidth: 0,
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  gap: 4,
                  maxWidth: '80%',
                }}>
                  {msg.chartConfig && <ChartDisplay config={msg.chartConfig} />}
                  <AnswerDisplay content={msg.content} title="智能问答 回答" />
                  <Text size={100} style={{ color: '#888', fontSize: 10 }}>
                    {fmtTime(msg.timestamp)}
                  </Text>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px' }}>
              <Spinner size="tiny" />
              <Text size={200}>智能分析中...</Text>
            </div>
          )}

          {error && (
            <MessageBar intent="error">
              <MessageBarBody>{error}</MessageBarBody>
            </MessageBar>
          )}

          <div ref={bottomRef} />
        </div>

        <div className={classes.inputArea}>
          <Input
            className={classes.inputField}
            ref={inputRef}
            value={input}
            onChange={(_, d) => setInput(d.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，按 Enter 发送"
            disabled={loading}
          />
          {loading ? (
            <Button
              appearance="subtle"
              icon={<StopRegular />}
              onClick={handleStop}
            >
              停止
            </Button>
          ) : (
            <Button
              appearance="primary"
              icon={<SendRegular />}
              onClick={handleSend}
              disabled={!input.trim()}
            >
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

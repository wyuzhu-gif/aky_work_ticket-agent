import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Input,
  Spinner,
  Text,
  MessageBar,
  MessageBarBody,
} from '@fluentui/react-components'
import { SendRegular, ChatRegular, StopRegular } from '@fluentui/react-icons'
import {
  useChatStyles,
  AnswerDisplay,
  ChartDisplay,
  fmtTime,
  type ChatMessage,
} from '../../components/chat'
import { agentChatStream, agentCancel, type AgentChatHandle } from '../../services/agentChatApi'

interface UiMessage extends ChatMessage {
  timestamp: string
  chartConfig?: Record<string, unknown>
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

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  const handleStop = useCallback(async () => {
    const h = currentHandleRef.current
    if (!h) return
    // 1) 主动 abort fetch (立即停前端 + 同步调 /cancel, 在 makeHandle 里)
    h.abort()
    // 2) 调服务端 cancel (停上游 hermes) - 优先 task_id (Phase 1)
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
    // 先 push user msg + 占位 ai msg (isStreaming=true)
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
        { question: q },
        {
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
            // 关键: 后端从 LLM 输出抽到 chartconfig 块
            // cleanedText 是剥掉 chartconfig 块的纯文本 (避免 markdown 重复)
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx
                ? { ...m, chartConfig, content: cleanedText || m.content }
                : m
            ))
          },
          onResponse: (respPayload) => {
            // 统一 schema 收尾 (Phase 2: 跟智能问数 SmartQuery 对齐)
            // 关键: 即使流中断 (partial=true), 也要把已有内容写回
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
            // partial 提示用户
            if (respPayload.partial) {
              setError(`⚠️ 响应被截断 (type=${respPayload.type}, trace=${respPayload.trace_id || '?'})`)
            }
          },
          onDone: (meta) => {
            // meta: { totalContent, traceId }
            // 注意: onResponse 已在 finally 块推过来, 这里不重复
            // 但要保证 loading 一定复位 (兜底)
            if (meta?.traceId) {
              // trace 已在 onResponse 拿过, 这里仅 logging
              // console.debug('[agent] stream done, trace:', meta.traceId)
            }
            setMessages(prev => prev.map((m, i) =>
              i === aiMsgIdx && m.isStreaming
                ? { ...m, isStreaming: false }
                : m
            ))
            setLoading(false)
            currentHandleRef.current = null
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
  }, [input, loading, messages.length])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={classes.root}>
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
                  width: '80%',         // 2026-06-25: 收紧到 80% (你要求)
                  minWidth: 0,
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  gap: 4,
                  maxWidth: '80%',      // 同步上限, 防止溢出
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

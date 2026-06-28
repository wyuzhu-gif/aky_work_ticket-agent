import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Input,
  Label,
  makeStyles,
  MessageBar,
  MessageBarBody,
  Spinner,
  Tab,
  TabList,
  Select,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  TabValue,
  Text,
  Textarea,
  tokens,
  Badge,
  Dialog,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tooltip,
} from '@fluentui/react-components'
import {
  BrainCircuitRegular,
  DatabaseRegular,
  BookRegular,
  SettingsRegular,
  SaveRegular,
  AddRegular,
  DeleteRegular,
  ArrowSyncRegular,
  CheckmarkRegular,
  CopyRegular,
  EditRegular,
} from '@fluentui/react-icons'
import type { LLMConfig, DBConfig, AgentConfig, TrainingItem } from '../../services/sqlagentAdminApi'
import {
  getLLMConfig, setLLMConfig, testLLM,
  getDBConfig, setDBConfig, testDB,
  getTrainingData, addTrainingData, deleteTrainingData,
  getAgentConfig, setAgentConfig,
} from '../../services/sqlagentAdminApi'

const useStyles = makeStyles({
  container: { display: 'flex', flexDirection: 'column', gap: '16px' },
  title: { fontSize: '20px', fontWeight: 700, color: tokens.colorBrandForeground1 },
  card: {
    padding: '20px',
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: '12px',
    backgroundColor: tokens.colorNeutralBackground1,
  },
  formGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
  },
  fullField: { gridColumn: '1 / -1' },
  fieldItem: { display: 'flex', flexDirection: 'column', gap: '4px' },
  fieldLabel: { fontSize: '12px', color: tokens.colorNeutralForeground3, fontWeight: 500 },
  actions: { display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '16px' },
  badge: { marginBottom: '12px' },
  empty: {
    textAlign: 'center',
    padding: '40px',
    color: tokens.colorNeutralForeground3,
  },
  tableWrap: { overflowX: 'auto' },
  addForm: { display: 'flex', flexDirection: 'column', gap: '12px' },
})

function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try { setData(await fn()) } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }, deps)
  return { data, loading, error, load, setData }
}

// ────────── LLM Tab ──────────
function LLMTab() {
  const classes = useStyles()
  const [form, setForm] = useState<LLMConfig>({ api_key: '', base_url: '', model_name: '', temperature: 0.1, max_tokens: 4096 })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<{ intent: 'success' | 'error'; text: string } | null>(null)
  const { load } = useAsync(getLLMConfig, [])

  useEffect(() => {
    (async () => {
      try {
        const cfg = await getLLMConfig()
        if (cfg.configured && cfg.base_url) {
          setForm({
            api_key: cfg.api_key === '******' ? '' : (cfg.api_key || ''),
            base_url: cfg.base_url || '',
            model_name: cfg.model_name || '',
            temperature: cfg.temperature ?? 0.1,
            max_tokens: cfg.max_tokens ?? 4096,
          })
        }
      } catch { /* ignore */ }
    })()
  }, [])

  const handleSave = async () => {
    setSaving(true); setMsg(null)
    try { await setLLMConfig(form); setMsg({ intent: 'success', text: '保存成功' }) }
    catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await testLLM(form)
      setMsg({ intent: r.success ? 'success' : 'error', text: r.message })
    } catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setTesting(false) }
  }

  const u = (k: keyof LLMConfig, v: string | number) => setForm(p => ({ ...p, [k]: v }))

  return (
    <div className={classes.card}>
      {msg && <MessageBar intent={msg.intent}><MessageBarBody>{msg.text}</MessageBarBody></MessageBar>}
      <div className={classes.formGrid}>
        <div className={classes.fullField}>
          <Label className={classes.fieldLabel}>API Base URL</Label>
          <Input value={form.base_url} onChange={(_, d) => u('base_url', d.value)} placeholder="https://api.openai.com/v1" />
        </div>
        <div className={classes.fullField}>
          <Label className={classes.fieldLabel}>API Key</Label>
          <Input type="password" value={form.api_key} onChange={(_, d) => u('api_key', d.value)} placeholder="sk-... (留空保持当前)" />
        </div>
        <div className={classes.fullField}>
          <Label className={classes.fieldLabel}>模型名称</Label>
          <Input value={form.model_name} onChange={(_, d) => u('model_name', d.value)} placeholder="qwen-flash / gpt-4o" />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>Temperature</Label>
          <Input type="number" value={String(form.temperature)} onChange={(_, d) => u('temperature', Number(d.value))} />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>Max Tokens</Label>
          <Input type="number" value={String(form.max_tokens)} onChange={(_, d) => u('max_tokens', Number(d.value))} />
        </div>
      </div>
      <div className={classes.actions}>
        <Button appearance="secondary" icon={testing ? <Spinner size="tiny" /> : <ArrowSyncRegular />} onClick={handleTest} disabled={testing || saving}>
          测试连接
        </Button>
        <Button appearance="primary" icon={saving ? <Spinner size="tiny" /> : <SaveRegular />} onClick={handleSave} disabled={saving || testing}>
          保存
        </Button>
      </div>
    </div>
  )
}

// ────────── DB Tab ──────────
function DBTab() {
  const classes = useStyles()
  const [form, setForm] = useState<DBConfig>({ db_type: 'postgresql', host: '', port: 5432, dbname: '', username: '', password: '' })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<{ intent: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    (async () => {
      try {
        const cfg = await getDBConfig()
        if (cfg.configured && cfg.host) {
          setForm({
            db_type: cfg.db_type || 'postgresql',
            host: cfg.host || '',
            port: cfg.port || 5432,
            dbname: cfg.dbname || '',
            username: cfg.username || '',
            password: cfg.password || '',
          })
        }
      } catch { /* ignore */ }
    })()
  }, [])

  const handleSave = async () => {
    setSaving(true); setMsg(null)
    try { await setDBConfig(form); setMsg({ intent: 'success', text: '保存成功' }) }
    catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await testDB(form)
      setMsg({ intent: r.success ? 'success' : 'error', text: r.message })
    } catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setTesting(false) }
  }

  const u = (k: keyof DBConfig, v: string | number) => setForm(p => ({ ...p, [k]: v }))

  return (
    <div className={classes.card}>
      {msg && <MessageBar intent={msg.intent}><MessageBarBody>{msg.text}</MessageBarBody></MessageBar>}
      <div className={classes.formGrid}>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>数据库类型</Label>
          <Select value={form.db_type} onChange={(_, d) => u('db_type', d.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
          </Select>
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>数据库名</Label>
          <Input value={form.dbname} onChange={(_, d) => u('dbname', d.value)} />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>Host</Label>
          <Input value={form.host} onChange={(_, d) => u('host', d.value)} />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>Port</Label>
          <Input type="number" value={String(form.port)} onChange={(_, d) => u('port', Number(d.value))} />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>用户名</Label>
          <Input value={form.username} onChange={(_, d) => u('username', d.value)} />
        </div>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>密码</Label>
          <Input type="password" value={form.password} onChange={(_, d) => u('password', d.value)} />
        </div>
      </div>
      <div className={classes.actions}>
        <Button appearance="secondary" icon={testing ? <Spinner size="tiny" /> : <ArrowSyncRegular />} onClick={handleTest} disabled={testing || saving}>
          测试连接
        </Button>
        <Button appearance="primary" icon={saving ? <Spinner size="tiny" /> : <SaveRegular />} onClick={handleSave} disabled={saving || testing}>
          保存
        </Button>
      </div>
    </div>
  )
}

// ────────── Training Tab ──────────
function TrainingTab() {
  const classes = useStyles()
  const [items, setItems] = useState<TrainingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<string>('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<'add' | 'edit' | 'copy'>('add')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [addType, setAddType] = useState<string>('ddl')
  const [addContent, setAddContent] = useState('')
  const [addQuestion, setAddQuestion] = useState('')
  const [addSql, setAddSql] = useState('')
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState<{ intent: 'success' | 'error'; text: string } | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const r = await getTrainingData(filter || undefined)
      setItems(r.data || [])
    } catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setLoading(false) }
  }, [filter])

  useEffect(() => { loadData() }, [loadData])

  const resetForm = () => {
    setAddType('ddl'); setAddContent(''); setAddQuestion(''); setAddSql('')
    setEditingId(null)
  }

  const openAddDialog = () => {
    resetForm()
    setDialogMode('add')
    setDialogOpen(true)
  }

  const openEditDialog = (item: TrainingItem) => {
    const t = item.training_data_type
    setAddType(t)
    if (t === 'sql') {
      setAddQuestion(item.question || '')
      setAddSql(item.sql || '')
      setAddContent('')
    } else {
      setAddContent(item.content || '')
      setAddQuestion('')
      setAddSql('')
    }
    setEditingId(item.id)
    setDialogMode('edit')
    setDialogOpen(true)
  }

  const openCopyDialog = (item: TrainingItem) => {
    const t = item.training_data_type
    setAddType(t)
    if (t === 'sql') {
      setAddQuestion(item.question || '')
      setAddSql(item.sql || '')
      setAddContent('')
    } else {
      setAddContent(item.content || '')
      setAddQuestion('')
      setAddSql('')
    }
    setEditingId(null)
    setDialogMode('copy')
    setDialogOpen(true)
  }

  const handleSave = async () => {
    setAdding(true)
    try {
      const payload: any = { training_type: addType }
      if (addType === 'ddl' || addType === 'documentation') payload.content = addContent
      if (addType === 'sql') { payload.question = addQuestion; payload.sql = addSql }

      if (dialogMode === 'edit' && editingId) {
        await deleteTrainingData(editingId)
      }
      await addTrainingData(payload)

      setDialogOpen(false)
      resetForm()
      setMsg({ intent: 'success', text: dialogMode === 'edit' ? '修改成功' : dialogMode === 'copy' ? '复制成功' : '添加成功' })
      loadData()
    } catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setAdding(false) }
  }

  const handleDelete = async (id: string) => {
    try { await deleteTrainingData(id); setMsg({ intent: 'success', text: '删除成功' }); loadData() }
    catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
  }

  const typeLabel = (t: string) => t === 'ddl' ? 'DDL' : t === 'sql' ? 'SQL 示例' : '文档'
  const dialogTitle = dialogMode === 'edit' ? '编辑训练数据' : dialogMode === 'copy' ? '复制训练数据' : '添加训练数据'

  return (
    <div className={classes.card}>
      {msg && <MessageBar intent={msg.intent}><MessageBarBody>{msg.text}</MessageBarBody></MessageBar>}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Label>类型筛选:</Label>
          <Select value={filter} onChange={(_, d) => setFilter(d.value)} style={{ minWidth: 120 }}>
            <option value="">全部</option>
            <option value="ddl">DDL</option>
            <option value="sql">SQL 示例</option>
            <option value="documentation">文档</option>
          </Select>
        </div>
        <Button appearance="primary" size="small" icon={<AddRegular />} onClick={openAddDialog}>添加</Button>
      </div>

      {loading ? <Spinner /> : items.length === 0 ? (
        <div className={classes.empty}><Text>暂无训练数据</Text></div>
      ) : (
        <div className={classes.tableWrap}>
          <Table size="small">
            <TableHeader>
              <TableRow>
                <TableHeaderCell style={{ width: 80 }}>类型</TableHeaderCell>
                <TableHeaderCell>内容摘要</TableHeaderCell>
                <TableHeaderCell style={{ width: 140 }}>操作</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map(item => (
                <TableRow key={item.id}>
                  <TableCell><Badge appearance="ghost" color="informative" size="small">{typeLabel(item.training_data_type)}</Badge></TableCell>
                  <TableCell><Text size={200} truncate>
                    {item.training_data_type === 'sql'
                      ? (item.question || '-')
                      : (item.content || '-').slice(0, 120)}
                  </Text></TableCell>
                  <TableCell>
                    <div style={{ display: 'flex', gap: 2 }}>
                      <Tooltip content="编辑" relationship="label">
                        <Button size="small" appearance="subtle" icon={<EditRegular />} onClick={() => openEditDialog(item)} />
                      </Tooltip>
                      <Tooltip content="复制" relationship="label">
                        <Button size="small" appearance="subtle" icon={<CopyRegular />} onClick={() => openCopyDialog(item)} />
                      </Tooltip>
                      <Tooltip content="删除" relationship="label">
                        <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => handleDelete(item.id)} />
                      </Tooltip>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={(_, d) => { if (!d.type) { setDialogOpen(false); resetForm() } }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>{dialogTitle}</DialogTitle>
            <DialogContent>
              <div className={classes.addForm}>
                <div className={classes.fieldItem}>
                  <Label className={classes.fieldLabel}>类型</Label>
                  <Select value={addType} onChange={(_, d) => setAddType(d.value)} disabled={dialogMode === 'edit'}>
                    <option value="ddl">DDL (表结构)</option>
                    <option value="documentation">文档 (业务说明)</option>
                    <option value="sql">SQL 示例 (问答对)</option>
                  </Select>
                </div>
                {(addType === 'ddl' || addType === 'documentation') && (
                  <div className={classes.fieldItem}>
                    <Label className={classes.fieldLabel}>{addType === 'ddl' ? 'DDL 语句' : '文档内容'}</Label>
                    <Textarea rows={10} value={addContent} onChange={(_, d) => setAddContent(d.value)} />
                  </div>
                )}
                {addType === 'sql' && (
                  <>
                    <div className={classes.fieldItem}>
                      <Label className={classes.fieldLabel}>问题</Label>
                      <Input value={addQuestion} onChange={(_, d) => setAddQuestion(d.value)} />
                    </div>
                    <div className={classes.fieldItem}>
                      <Label className={classes.fieldLabel}>SQL</Label>
                      <Textarea rows={6} value={addSql} onChange={(_, d) => setAddSql(d.value)} />
                    </div>
                  </>
                )}
              </div>
            </DialogContent>
            <DialogActions>
              <Button appearance="subtle" onClick={() => { setDialogOpen(false); resetForm() }}>取消</Button>
              <Button appearance="primary" icon={adding ? <Spinner size="tiny" /> : <CheckmarkRegular />} onClick={handleSave} disabled={adding}>
                {dialogMode === 'edit' ? '保存修改' : dialogMode === 'copy' ? '添加副本' : '添加'}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  )
}

// ────────── Agent Config Tab ──────────
function AgentConfigTab() {
  const classes = useStyles()
  const [greeting, setGreeting] = useState('')
  const [questions, setQuestions] = useState<string[]>([])
  const [prompt, setPrompt] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ intent: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    (async () => {
      try {
        const cfg = await getAgentConfig()
        setGreeting(cfg.greeting || '')
        setQuestions(cfg.example_questions || [])
        setPrompt(cfg.custom_prompt || '')
      } catch { /* ignore */ }
    })()
  }, [])

  const handleSave = async () => {
    setSaving(true); setMsg(null)
    try {
      await setAgentConfig({ greeting, example_questions: questions, custom_prompt: prompt })
      setMsg({ intent: 'success', text: '保存成功' })
    } catch (e: any) { setMsg({ intent: 'error', text: e.message }) }
    finally { setSaving(false) }
  }

  const addQuestion = () => setQuestions(p => [...p, ''])
  const updateQuestion = (i: number, v: string) => setQuestions(p => { const n = [...p]; n[i] = v; return n })
  const removeQuestion = (i: number) => setQuestions(p => p.filter((_, idx) => idx !== i))

  return (
    <div className={classes.card}>
      {msg && <MessageBar intent={msg.intent}><MessageBarBody>{msg.text}</MessageBarBody></MessageBar>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>欢迎语</Label>
          <Input value={greeting} onChange={(_, d) => setGreeting(d.value)} placeholder="用户进入对话时显示的欢迎语" />
        </div>

        <div className={classes.fieldItem}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Label className={classes.fieldLabel}>示例问题</Label>
            <Button size="small" appearance="subtle" icon={<AddRegular />} onClick={addQuestion}>添加</Button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            {questions.map((q, i) => (
              <div key={i} style={{ display: 'flex', gap: 8 }}>
                <Input style={{ flex: 1 }} value={q} onChange={(_, d) => updateQuestion(i, d.value)} placeholder={`示例问题 ${i + 1}`} />
                <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => removeQuestion(i)} />
              </div>
            ))}
          </div>
        </div>

        <div className={classes.fieldItem}>
          <Label className={classes.fieldLabel}>自定义提示词（追加到系统提示词末尾）</Label>
          <Textarea rows={8} value={prompt} onChange={(_, d) => setPrompt(d.value)} placeholder="例如：当前数据库是作业票系统，用户会问关于动火作业、受限空间等问题..." />
        </div>
      </div>

      <div className={classes.actions}>
        <Button appearance="primary" icon={saving ? <Spinner size="tiny" /> : <SaveRegular />} onClick={handleSave} disabled={saving}>
          保存
        </Button>
      </div>
    </div>
  )
}

// ────────── Main Page ──────────
export default function AgentAdmin() {
  const classes = useStyles()
  const [tab, setTab] = useState<TabValue>('llm')

  return (
    <div className={classes.container}>
      <Text className={classes.title}>智能问数智能体管理</Text>

      <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(d.value)}>
        <Tab value="llm" icon={<BrainCircuitRegular />}>大模型配置</Tab>
        <Tab value="db" icon={<DatabaseRegular />}>数据库配置</Tab>
        <Tab value="training" icon={<BookRegular />}>训练数据</Tab>
        <Tab value="agent" icon={<SettingsRegular />}>智能体配置</Tab>
      </TabList>

      {tab === 'llm' && <LLMTab />}
      {tab === 'db' && <DBTab />}
      {tab === 'training' && <TrainingTab />}
      {tab === 'agent' && <AgentConfigTab />}
    </div>
  )
}

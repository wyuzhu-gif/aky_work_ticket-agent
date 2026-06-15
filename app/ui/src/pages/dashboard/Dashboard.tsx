import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  CardHeader,
  CardPreview,
  makeStyles,
  tokens,
  Subtitle1,
  Subtitle2,
  Body1,
  Body2,
  Caption1,
  ProgressBar,
  Spinner,
  Button,
} from '@fluentui/react-components'
import {
  DocumentBulletListRegular,
  ShieldCheckmarkRegular,
  AlertRegular,
  CheckmarkCircleRegular,
  DismissCircleRegular,
  ClockRegular,
  WarningRegular,
} from '@fluentui/react-icons'
import {
  fetchDashboard,
  type DashboardResponse,
  type RecentReview,
  type PermitTypeStat,
} from '../../services/dashboardApi'

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
    padding: '24px',
    maxWidth: '1200px',
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '16px',
  },
  statCard: {
    cursor: 'default',
  },
  statValue: {
    fontSize: '28px',
    fontWeight: 600,
    lineHeight: 1.2,
  },
  statLabel: {
    color: tokens.colorNeutralForeground3,
    marginTop: '4px',
  },
  twoCol: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
  },
  sectionCard: {
    minHeight: '280px',
  },
  listRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 0',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    cursor: 'pointer',
    '&:last-child': { borderBottom: 'none' },
    '&:hover': { backgroundColor: tokens.colorNeutralBackground1Hover },
  },
  riskBar: {
    display: 'flex',
    gap: '4px',
    height: '24px',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  riskSegment: {
    transition: 'width 0.3s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  permitRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 0',
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    '&:last-child': { borderBottom: 'none' },
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px 20px',
    color: tokens.colorNeutralForeground3,
  },
})

// 指标卡片配置
const STAT_CARDS = [
  { key: 'total_reviews', label: '审核文档', icon: DocumentBulletListRegular, color: tokens.colorBrandForeground1 },
  { key: 'total_issues', label: '发现问题', icon: AlertRegular, color: tokens.colorPaletteRedForeground1 },
  { key: 'high_risk_issues', label: '高风险', icon: WarningRegular, color: tokens.colorPaletteRedForeground3 },
  { key: 'total_permits', label: '作业票', icon: ShieldCheckmarkRegular, color: tokens.colorPaletteBlueForeground1 },
] as const

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function riskColor(level: string): string {
  switch (level) {
    case 'high': return tokens.colorPaletteRedBackground3
    case 'medium': return tokens.colorPaletteOrangeBackground3
    case 'low': return tokens.colorPaletteGreenBackground3
    default: return tokens.colorNeutralBackground3
  }
}

export default function Dashboard() {
  const classes = useStyles()
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [period, setPeriod] = useState<'today' | 'week' | 'month' | 'all'>('all')

  useEffect(() => {
    setLoading(true)
    fetchDashboard(period)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) {
    return (
      <div className={classes.emptyState}>
        <Spinner size="large" label="加载看板数据..." />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className={classes.emptyState}>
        <Body1>加载失败: {error}</Body1>
        <Button appearance="primary" onClick={() => window.location.reload()} style={{ marginTop: 12 }}>
          重试
        </Button>
      </div>
    )
  }

  const { stats, recent_reviews, permit_type_stats, risk_distribution } = data
  const totalRisk = risk_distribution.high + risk_distribution.medium + risk_distribution.low + risk_distribution.info || 1

  return (
    <div className={classes.root}>
      {/* 标题栏 + 时间筛选 */}
      <div className={classes.header}>
        <Subtitle1>审核看板</Subtitle1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {([['today', '今日'], ['week', '本周'], ['month', '本月'], ['all', '全部']] as const).map(([val, label]) => (
            <Button
              key={val}
              size="small"
              appearance={period === val ? 'primary' : 'subtle'}
              onClick={() => setPeriod(val)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {/* 指标卡片 */}
      <div className={classes.statsGrid}>
        {STAT_CARDS.map(({ key, label, icon: Icon, color }) => (
          <Card key={key} className={classes.statCard}>
            <CardPreview style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px' }}>
              <Icon style={{ fontSize: 28, color }} />
              <div>
                <div className={classes.statValue} style={{ color }}>
                  {stats[key as keyof typeof stats] as number}
                </div>
                <div className={classes.statLabel}>{label}</div>
              </div>
            </CardPreview>
          </Card>
        ))}

        {/* 已采纳/已驳回/待处理 小卡片 */}
        <Card className={classes.statCard}>
          <CardPreview style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <div style={{ textAlign: 'center' }}>
                <CheckmarkCircleRegular style={{ fontSize: 20, color: tokens.colorPaletteGreenForeground1 }} />
                <div style={{ fontWeight: 600 }}>{stats.accepted_issues}</div>
                <Caption1>已采纳</Caption1>
              </div>
              <div style={{ textAlign: 'center' }}>
                <DismissCircleRegular style={{ fontSize: 20, color: tokens.colorNeutralForeground3 }} />
                <div style={{ fontWeight: 600 }}>{stats.dismissed_issues}</div>
                <Caption1>已驳回</Caption1>
              </div>
              <div style={{ textAlign: 'center' }}>
                <ClockRegular style={{ fontSize: 20, color: tokens.colorPaletteOrangeForeground1 }} />
                <div style={{ fontWeight: 600 }}>{stats.pending_issues}</div>
                <Caption1>待处理</Caption1>
              </div>
            </div>
          </CardPreview>
        </Card>
      </div>

      {/* 两栏：最近审核 + 风险分布 / 作业票统计 */}
      <div className={classes.twoCol}>
        {/* 左栏：最近审核记录 */}
        <Card className={classes.sectionCard}>
          <CardHeader
            header={<Subtitle2>最近审核记录</Subtitle2>}
          />
          <div style={{ padding: '0 16px 16px' }}>
            {recent_reviews.length === 0 ? (
              <div className={classes.emptyState} style={{ padding: 20 }}>
                <Body2>暂无审核记录</Body2>
              </div>
            ) : (
              recent_reviews.map((r: RecentReview) => (
                <div
                  key={r.doc_id}
                  className={classes.listRow}
                  onClick={() => navigate(`/review?document=${encodeURIComponent(r.doc_id)}`)}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Body2 style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.doc_id}
                    </Body2>
                    <Caption1>{formatTime(r.latest_review_time)}</Caption1>
                  </div>
                  <div style={{ display: 'flex', gap: 12, flexShrink: 0 }}>
                    {r.high_risk_count > 0 && (
                      <span style={{ color: tokens.colorPaletteRedForeground1, fontWeight: 600, fontSize: 13 }}>
                        ⚠ {r.high_risk_count}
                      </span>
                    )}
                    <Caption1>{r.issue_count} 问题</Caption1>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* 右栏：风险分布 + 作业票统计 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 风险分布 */}
          <Card>
            <CardHeader header={<Subtitle2>风险等级分布</Subtitle2>} />
            <div style={{ padding: '0 16px 16px' }}>
              <div className={classes.riskBar}>
                {risk_distribution.high > 0 && (
                  <div className={classes.riskSegment} style={{ width: `${(risk_distribution.high / totalRisk) * 100}%`, backgroundColor: riskColor('high') }}>
                    <Caption1 style={{ color: '#fff' }}>{risk_distribution.high}</Caption1>
                  </div>
                )}
                {risk_distribution.medium > 0 && (
                  <div className={classes.riskSegment} style={{ width: `${(risk_distribution.medium / totalRisk) * 100}%`, backgroundColor: riskColor('medium') }}>
                    <Caption1>{risk_distribution.medium}</Caption1>
                  </div>
                )}
                {risk_distribution.low > 0 && (
                  <div className={classes.riskSegment} style={{ width: `${(risk_distribution.low / totalRisk) * 100}%`, backgroundColor: riskColor('low') }}>
                    <Caption1>{risk_distribution.low}</Caption1>
                  </div>
                )}
                {risk_distribution.info > 0 && (
                  <div className={classes.riskSegment} style={{ width: `${(risk_distribution.info / totalRisk) * 100}%`, backgroundColor: riskColor('info') }}>
                    <Caption1>{risk_distribution.info}</Caption1>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 16, marginTop: 8, justifyContent: 'center' }}>
                <Caption1><span style={{ color: riskColor('high') }}>●</span> 高风险 {risk_distribution.high}</Caption1>
                <Caption1><span style={{ color: riskColor('medium') }}>●</span> 中风险 {risk_distribution.medium}</Caption1>
                <Caption1><span style={{ color: riskColor('low') }}>●</span> 低风险 {risk_distribution.low}</Caption1>
                <Caption1><span style={{ color: riskColor('info') }}>●</span> 提示 {risk_distribution.info}</Caption1>
              </div>
            </div>
          </Card>

          {/* 作业票统计 */}
          <Card>
            <CardHeader header={<Subtitle2>作业票统计</Subtitle2>} />
            <div style={{ padding: '0 16px 16px' }}>
              {permit_type_stats.map((pt: PermitTypeStat) => (
                <div key={pt.type} className={classes.permitRow}>
                  <Body2>{pt.label}</Body2>
                  <Body2 style={{ fontWeight: 600 }}>{pt.count}</Body2>
                </div>
              ))}
              <div className={classes.permitRow} style={{ borderBottom: 'none', borderTop: `1px solid ${tokens.colorNeutralStroke2}`, marginTop: 4, paddingTop: 8 }}>
                <Subtitle2>合计</Subtitle2>
                <Subtitle2 style={{ fontWeight: 700 }}>{stats.total_permits}</Subtitle2>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/pages/report/Report.tsx'
content = r'''import { Button, makeStyles, tokens, Badge } from '@fluent-ui/react-components'
import { ArrowLeftRegular, PrintRegular } from '@fluent-ui/react-icons'
import { useLocation, useNavigate } from 'react-router-dom'
import { Issue } from '../../types/issue'
import { issueRiskLevel } from '../../i18n/labels'

const useStyles = makeStyles({
  page: {
    display: 'flex',
    flexDirection: 'column',
    minHeight: '100vh',
    backgroundColor: tokens.colorNeutralBackground3,
  },
  toolbar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 24px',
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    '@media print': {
      display: 'none !important',
    },
  },
  paper: {
    maxWidth: '800px',
    width: '100%',
    margin: '24px auto',
    padding: '40px 48px',
    backgroundColor: tokens.colorNeutralBackground1,
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    '@media print': {
      margin: 0,
      padding: '20px',
      boxShadow: 'none',
      borderRadius: 0,
      maxWidth: 'none',
    },
  },
  reportTitle: {
    fontSize: '22px',
    fontWeight: 700,
    color: tokens.colorNeutralForeground1,
    textAlign: 'center',
    marginBottom: '4px',
  },
  reportSubtitle: {
    fontSize: '13px',
    color: tokens.colorNeutralForeground3,
    textAlign: 'center',
    marginBottom: '20px',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
    marginBottom: '24px',
    padding: '16px',
    backgroundColor: tokens.colorNeutralBackground2,
    borderRadius: '8px',
  },
  summaryItem: {
    textAlign: 'center',
  },
  summaryValue: {
    fontSize: '20px',
    fontWeight: 700,
    color: tokens.colorNeutralForeground1,
  },
  summaryLabel: {
    fontSize: '11px',
    color: tokens.colorNeutralForeground3,
    marginTop: '2px',
  },
  divider: {
    border: 'none',
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    margin: '20px 0',
  },
  issueCard: {
    padding: '16px 0',
    borderBottom: `1px solid ${tokens.colorNeutralStroke3}`,
    breakInside: 'avoid',
    '@media print': {
      borderBottom: `1px solid #ddd`,
    },
  },
  issueHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '10px',
    flexWrap: 'wrap',
  },
  issueNumber: {
    fontSize: '15px',
    fontWeight: 700,
    color: tokens.colorBrandForeground1,
  },
  fieldBlock: {
    marginBottom: '8px',
  },
  fieldLabel: {
    fontSize: '11px',
    fontWeight: 600,
    color: tokens.colorNeutralForeground3,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '3px',
  },
  fieldContent: {
    fontSize: '13px',
    lineHeight: '1.6',
    color: tokens.colorNeutralForeground1,
    outline: 'none',
    borderRadius: '4px',
    padding: '4px 6px',
    border: '1px solid transparent',
    minHeight: '1.6em',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground2,
    },
    ':focus': {
      border: `1px solid ${tokens.colorBrandStroke1}`,
      backgroundColor: tokens.colorNeutralBackground2,
    },
    '@media print': {
      border: 'none',
      padding: 0,
    },
  },
  modifiedBadge: {
    fontSize: '10px',
    marginLeft: '4px',
  },
  emptyState: {
    textAlign: 'center',
    padding: '60px 20px',
    color: tokens.colorNeutralForeground3,
  },
  emptyTitle: {
    fontSize: '16px',
    fontWeight: 600,
    marginBottom: '8px',
  },
})

function displayValue(original: string, modifiedField?: string | null): string {
  return modifiedField ?? original
}

function hasModifications(issue: Issue): boolean {
  const mf = issue.modified_fields
  if (!mf) return false
  return (
    (mf.text !== undefined && mf.text !== issue.text) ||
    (mf.explanation !== undefined && mf.explanation !== issue.explanation) ||
    (mf.suggested_fix !== undefined && mf.suggested_fix !== issue.suggested_fix)
  )
}

export default function Report() {
  const classes = useStyles()
  const location = useLocation()
  const navigate = useNavigate()
  const state = location.state as { docId?: string; issues?: Issue[] } | null
  const docId = state?.docId ?? ''
  const issues = state?.issues ?? []

  if (!issues.length) {
    return (
      <div className={classes.page}>
        <div className={classes.toolbar}>
          <Button icon={<ArrowLeftRegular />} onClick={() => navigate(-1)}>
            返回审阅
          </Button>
        </div>
        <div className={classes.emptyState}>
          <div className={classes.emptyTitle}>无已采纳的问题</div>
          <div>请返回审阅页面采纳问题后，再导出报告。</div>
        </div>
      </div>
    )
  }

  const high = issues.filter(i => issueRiskLevel(i.type, i.risk_level) === '高').length
  const medium = issues.filter(i => issueRiskLevel(i.type, i.risk_level) === '中').length
  const low = issues.filter(i => issueRiskLevel(i.type, i.risk_level) === '低').length
  const modified = issues.filter(hasModifications).length

  return (
    <div className={classes.page}>
      <div className={classes.toolbar}>
        <Button icon={<ArrowLeftRegular />} onClick={() => navigate(-1)}>
          返回审阅
        </Button>
        <Button
          appearance="primary"
          icon={<PrintRegular />}
          onClick={() => window.print()}
        >
          打印 / 导出 PDF
        </Button>
      </div>

      <div className={classes.paper}>
        <div className={classes.reportTitle} contentEditable suppressContentEditableWarning>
          审阅报告
        </div>
        <div className={classes.reportSubtitle}>
          文档：{docId} &nbsp;|&nbsp; 审阅日期：{new Date().toLocaleDateString('zh-CN')}
        </div>

        <div className={classes.summaryGrid}>
          <div className={classes.summaryItem}>
            <div className={classes.summaryValue}>{issues.length}</div>
            <div className={classes.summaryLabel}>已采纳问题</div>
          </div>
          <div className={classes.summaryItem}>
            <div className={classes.summaryValue} style={{ color: '#d13438' }}>{high}</div>
            <div className={classes.summaryLabel}>高风险</div>
          </div>
          <div className={classes.summaryItem}>
            <div className={classes.summaryValue} style={{ color: '#e69138' }}>{medium}</div>
            <div className={classes.summaryLabel}>中风险</div>
          </div>
          <div className={classes.summaryItem}>
            <div className={classes.summaryValue} style={{ color: '#107c10' }}>{low}</div>
            <div className={classes.summaryLabel}>低风险</div>
          </div>
        </div>

        <hr className={classes.divider} />

        {issues
          .sort((a, b) => (a.location?.page_num ?? 0) - (b.location?.page_num ?? 0))
          .map((issue, idx) => (
            <div key={issue.id} className={classes.issueCard}>
              <div className={classes.issueHeader}>
                <span className={classes.issueNumber}>#{idx + 1}</span>
                <Badge appearance="tint" shape="rounded" color={
                  issueRiskLevel(issue.type, issue.risk_level) === '高' ? 'danger' :
                  issueRiskLevel(issue.type, issue.risk_level) === '低' ? 'success' : 'warning'
                }>
                  {issueRiskLevel(issue.type, issue.risk_level)}风险
                </Badge>
                <Badge appearance="outline" shape="rounded">P{issue.location?.page_num ?? '-'}</Badge>
                <Badge appearance="outline" shape="rounded">{issue.type}</Badge>
                {hasModifications(issue) && (
                  <Badge appearance="filled" color="warning" className={classes.modifiedBadge}>
                    已修改
                  </Badge>
                )}
              </div>

              <div className={classes.fieldBlock}>
                <div className={classes.fieldLabel}>问题描述</div>
                <div
                  className={classes.fieldContent}
                  contentEditable
                  suppressContentEditableWarning
                >
                  {displayValue(issue.text, issue.modified_fields?.text)}
                </div>
              </div>

              <div className={classes.fieldBlock}>
                <div className={classes.fieldLabel}>问题说明</div>
                <div
                  className={classes.fieldContent}
                  contentEditable
                  suppressContentEditableWarning
                >
                  {displayValue(issue.explanation, issue.modified_fields?.explanation)}
                </div>
              </div>

              <div className={classes.fieldBlock}>
                <div className={classes.fieldLabel}>修改建议</div>
                <div
                  className={classes.fieldContent}
                  contentEditable
                  suppressContentEditableWarning
                >
                  {displayValue(issue.suggested_fix, issue.modified_fields?.suggested_fix)}
                </div>
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Created Report.tsx")
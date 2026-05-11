path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/pages/review/Review.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add PrintRegular icon import
content = content.replace(
    "import { useNavigate, useSearchParams } from 'react-router-dom'",
    "import { useNavigate, useSearchParams } from 'react-router-dom'\nimport { PrintRegular } from '@fluent-ui/react-icons'"
)

# Add export button before the "返回" button
# We need to compute accepted issues and pass them via navigate
content = content.replace(
    '''<Button size="small" appearance="secondary" onClick={() => navigate('/')}>
              返回
            </Button>''',
    '''<Button
              size="small"
              appearance="secondary"
              icon={<PrintRegular />}
              disabled={issues.filter(i => normalizeIssueStatus(i.status as any) === 'accepted').length === 0}
              onClick={() => {
                const accepted = issues.filter(i => normalizeIssueStatus(i.status as any) === 'accepted')
                navigate('/report', { state: { docId: docId ?? '', issues: accepted } })
              }}
            >
              导出报告
            </Button>
            <Button size="small" appearance="secondary" onClick={() => navigate('/')}>
              返回
            </Button>'''
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Added export button to Review.tsx")
path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/pages/report/Report.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix import paths
content = content.replace(
    "import { Button, makeStyles, tokens, Badge } from '@fluent-ui/react-components'",
    "import { Button, makeStyles, tokens, Badge } from '@fluentui/react-components'"
)
content = content.replace(
    "import { ArrowLeftRegular, PrintRegular } from '@fluent-ui/react-icons'",
    "import { ArrowLeftRegular, PrintRegular } from '@fluentui/react-icons'"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed import paths in Report.tsx")
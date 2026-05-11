path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/pages/review/Review.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "import { PrintRegular } from '@fluent-ui/react-icons'",
    "import { PrintRegular } from '@fluentui/react-icons'"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed PrintRegular import in Review.tsx")
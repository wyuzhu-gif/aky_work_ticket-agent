path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/types/issue.ts'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''export interface ModifiedFields {
  suggested_fix?: string
  explanation?: string
}'''

new = '''export interface ModifiedFields {
  suggested_fix?: string
  explanation?: string
  text?: string
}'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Added text to ModifiedFields")
else:
    print("SKIP")
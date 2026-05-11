path = '/data/lvm_data_48T/wyuz/ai-document-review/common/models.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''class ModifiedFieldsModel(BaseModel):
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None'''

new = '''class ModifiedFieldsModel(BaseModel):
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None
    text: Optional[str] = None'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Added text to ModifiedFieldsModel")
else:
    print("SKIP - already changed or not found")
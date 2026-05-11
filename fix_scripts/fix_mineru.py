path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'pdf_path, hl_text, hl_page, logging, mineru_payload=mineru_payload',
    'pdf_path, hl_text, hl_page, logging'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
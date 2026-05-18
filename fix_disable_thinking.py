"""Disable qwen3.5-flash thinking mode so content is returned in resp.content"""

path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/permits_service.py'
with open(path, 'r') as f:
    content = f.read()

# Disable thinking mode in _init_llm
old_init = """    def _init_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.1,
        )"""

new_init = """    def _init_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.1,
            extra_body={"enable_thinking": False},
        )"""

if old_init in content:
    content = content.replace(old_init, new_init)
    print('thinking mode disabled in _init_llm')
else:
    print('WARNING: _init_llm block not found')

with open(path, 'w') as f:
    f.write(content)
print('done')

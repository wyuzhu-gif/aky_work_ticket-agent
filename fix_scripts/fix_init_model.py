path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''def _init_deepseek_model():
    """
    Initialize DeepSeek chat model using LangChain v1 init_chat_model provider API.
    Falls back to OpenAI-compatible ChatOpenAI with custom base_url if provider package isn't available.
    """
    try:
        from langchain.chat_models import init_chat_model

        # langchain-deepseek reads DEEPSEEK_API_KEY from env by default.
        if settings.deepseek_api_key:
            import os

            os.environ.setdefault("DEEPSEEK_API_KEY", settings.deepseek_api_key)
        model_name = settings.deepseek_model or "deepseek-chat"
        return init_chat_model(model_name, model_provider="deepseek", temperature=0.2)
    except Exception as e:
        logging.warning(f"init_chat_model(deepseek) unavailable, falling back to ChatOpenAI: {e}")
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.2,
        )'''

new_func = '''def _init_deepseek_model():
    """
    Initialize chat model via ChatOpenAI (OpenAI-compatible).
    Works with DeepSeek, DashScope/Qwen, or any OpenAI-compatible endpoint.
    Uses DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL from settings/.env.
    """
    logging.info(
        f"Initializing LLM: base_url={settings.deepseek_base_url}, "
        f"model={settings.deepseek_model}"
    )
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=0.2,
    )'''

if old_func in content:
    content = content.replace(old_func, new_func)
    print("Replaced _init_deepseek_model successfully")
else:
    print("ERROR: Could not find exact match for _init_deepseek_model")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
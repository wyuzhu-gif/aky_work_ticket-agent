"""Fix: handle qwen3.5-flash thinking model returning empty content"""

path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/permits_service.py'
with open(path, 'r') as f:
    content = f.read()

fallback_code = """        # qwen3.5-flash thinking model: content may be empty, check reasoning_content
        if not raw or not raw.strip():
            reasoning = getattr(resp, 'additional_kwargs', {}).get('reasoning_content', '')
            if reasoning:
                logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
                raw = reasoning
"""

# Fix 1: compliance_review method - after "raw = resp.content"
# This block appears first (around line 367)
old_block1 = """        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        raw = re.sub(r"^```(?:json)?\\s*", "", raw.strip())
        raw = re.sub(r"\\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Compliance review returned non-JSON: {raw[:500]}")"""

new_block1 = """        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        # qwen3.5-flash thinking model: content may be empty, check reasoning_content
        if not raw or not raw.strip():
            reasoning = getattr(resp, 'additional_kwargs', {}).get('reasoning_content', '')
            if reasoning:
                logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
                raw = reasoning
        raw = re.sub(r"^```(?:json)?\\s*", "", raw.strip())
        raw = re.sub(r"\\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Compliance review returned non-JSON: {raw[:500]}")"""

# Fix 2: _extract_with_llm method - after "raw = resp.content"
old_block2 = """        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\\s*", "", raw.strip())
        raw = re.sub(r"\\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"LLM returned non-JSON: {raw[:500]}")"""

new_block2 = """        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        # qwen3.5-flash thinking model: content may be empty, check reasoning_content
        if not raw or not raw.strip():
            reasoning = getattr(resp, 'additional_kwargs', {}).get('reasoning_content', '')
            if reasoning:
                logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
                raw = reasoning
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\\s*", "", raw.strip())
        raw = re.sub(r"\\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"LLM returned non-JSON: {raw[:500]}")"""

# Apply compliance_review fix first (appears earlier in file)
if old_block1 in content:
    content = content.replace(old_block1, new_block1)
    print('compliance_review fix applied')
else:
    print('WARNING: compliance_review block not found')

# Apply _extract_with_llm fix second
if old_block2 in content:
    content = content.replace(old_block2, new_block2)
    print('_extract_with_llm fix applied')
else:
    print('WARNING: _extract_with_llm block not found')

with open(path, 'w') as f:
    f.write(content)

print('done')

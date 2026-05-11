path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add logging after LLM response and after parse
old_block = '''            # Parse using PydanticOutputParser (no provider-side response_format).
            out = self.parser.parse(str(content))
            raw_issues = out.issues
        except Exception as e:
            logging.error(f"LLM output parse failed: {e}")
            return []

        # === Agent 2: Intelligent highlight positioning ==='''

new_block = '''            # Log Agent 1 raw response
            logging.info(f"Agent 1 raw response length: {len(str(content))} chars")
            logging.info(f"Agent 1 response preview: {str(content)[:500]}")
            # Parse using PydanticOutputParser (no provider-side response_format).
            out = self.parser.parse(str(content))
            raw_issues = out.issues
            logging.info(f"Agent 1 parsed {len(raw_issues)} issues")
        except Exception as e:
            logging.error(f"LLM output parse failed: {e}")
            return []

        # === Agent 2: Intelligent highlight positioning ==='''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Added Agent 1 logging successfully")
else:
    print("ERROR: Could not find exact match for logging block")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
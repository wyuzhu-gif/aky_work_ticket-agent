path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/App.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add Report import
content = content.replace(
    'import RuleLibrary from "./pages/ruleLibrary/RuleLibrary";',
    'import RuleLibrary from "./pages/ruleLibrary/RuleLibrary";\nimport Report from "./pages/report/Report";'
)

# Add route
content = content.replace(
    '<Route path="/review" element={<Review />} />',
    '<Route path="/review" element={<Review />} />\n          <Route path="/report" element={<Report />} />'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated App.tsx with /report route")
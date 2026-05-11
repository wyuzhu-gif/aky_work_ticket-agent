path = '/data/lvm_data_48T/wyuz/ai-document-review/app/ui/src/components/IssueDetailsPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update buildModifiedFields to include text
content = content.replace(
    'function buildModifiedFields(modifiedExplanation?: string, modifiedSuggestedFix?: string): ModifiedFields | undefined {\n  const modifiedFields: ModifiedFields = {}\n  if (modifiedExplanation) modifiedFields.explanation = modifiedExplanation\n  if (modifiedSuggestedFix) modifiedFields.suggested_fix = modifiedSuggestedFix\n  return Object.keys(modifiedFields).length ? modifiedFields : undefined\n}',
    'function buildModifiedFields(modifiedText?: string, modifiedExplanation?: string, modifiedSuggestedFix?: string): ModifiedFields | undefined {\n  const modifiedFields: ModifiedFields = {}\n  if (modifiedText) modifiedFields.text = modifiedText\n  if (modifiedExplanation) modifiedFields.explanation = modifiedExplanation\n  if (modifiedSuggestedFix) modifiedFields.suggested_fix = modifiedSuggestedFix\n  return Object.keys(modifiedFields).length ? modifiedFields : undefined\n}'
)

# 2. Add modifiedText state
content = content.replace(
    "const [modifiedExplanation, setModifiedExplanation] = useState<string>()\n  const [modifiedSuggestedFix, setModifiedSuggestedFix] = useState<string>()",
    "const [modifiedText, setModifiedText] = useState<string>()\n  const [modifiedExplanation, setModifiedExplanation] = useState<string>()\n  const [modifiedSuggestedFix, setModifiedSuggestedFix] = useState<string>()"
)

# 3. Update defaults to include text
content = content.replace(
    "if (!current) return { explanation: '', suggestedFix: '' }\n    return {\n      explanation: current.modified_fields?.explanation ?? current.explanation,\n      suggestedFix: current.modified_fields?.suggested_fix ?? current.suggested_fix,\n    }",
    "if (!current) return { text: '', explanation: '', suggestedFix: '' }\n    return {\n      text: current.modified_fields?.text ?? current.text,\n      explanation: current.modified_fields?.explanation ?? current.explanation,\n      suggestedFix: current.modified_fields?.suggested_fix ?? current.suggested_fix,\n    }"
)

# 4. Reset modifiedText on issue change
content = content.replace(
    "setModifiedExplanation(undefined)\n    setModifiedSuggestedFix(undefined)\n    setError(undefined)",
    "setModifiedText(undefined)\n    setModifiedExplanation(undefined)\n    setModifiedSuggestedFix(undefined)\n    setError(undefined)"
)

# 5. Update handleAccept to pass modifiedText
content = content.replace(
    'buildModifiedFields(modifiedExplanation, modifiedSuggestedFix),\n      )\n      const updatedIssue = (await response.json()) as Issue\n      onUpdate(updatedIssue)',
    'buildModifiedFields(modifiedText, modifiedExplanation, modifiedSuggestedFix),\n      )\n      const updatedIssue = (await response.json()) as Issue\n      onUpdate(updatedIssue)'
)

# 6. Update openHitlEditDialog to pass modifiedText
content = content.replace(
    'modified_fields: buildModifiedFields(modifiedExplanation, modifiedSuggestedFix),',
    'modified_fields: buildModifiedFields(modifiedText, modifiedExplanation, modifiedSuggestedFix),'
)

# 7. Replace header card with editable text field
content = content.replace(
    '''{/* Issue Header Card */}
      <Card className={classes.panel}>
        <CardHeader
          header={<span className={classes.headerTitle}>{current.text}</span>}
          description={
            <div className={classes.headerMeta}>
              <Badge appearance="tint" shape="rounded" color={issueRiskTone(current.type, current.risk_level)}>
                {issueRiskLevel(current.type, current.risk_level)}风险
              </Badge>
              <Badge appearance="outline" shape="rounded" color="informative">
                {issueTypeLabel(current.type)}
              </Badge>
              <span className={classes.pageTag}>P{current.location?.page_num ?? '-'}</span>
              <span className={classes.statusTag}>{issueStatusLabel(normalizedStatus)}</span>
            </div>
          }
        />
      </Card>''',
    '''{/* Issue Header Card */}
      <Card className={classes.panel}>
        <div className={classes.formSection}>
          <div className={classes.headerMeta}>
            <Badge appearance="tint" shape="rounded" color={issueRiskTone(current.type, current.risk_level)}>
              {issueRiskLevel(current.type, current.risk_level)}风险
            </Badge>
            <Badge appearance="outline" shape="rounded" color="informative">
              {issueTypeLabel(current.type)}
            </Badge>
            <span className={classes.pageTag}>P{current.location?.page_num ?? '-'}</span>
            <span className={classes.statusTag}>{issueStatusLabel(normalizedStatus)}</span>
          </div>
          <Field label={<span className={classes.fieldLabel}>问题描述</span>}>
            <Textarea
              className={classes.textareaField}
              readOnly={!editable}
              value={modifiedText ?? defaults.text}
              onChange={(e) => setModifiedText(e.target.value)}
              rows={3}
              resize="vertical"
            />
          </Field>
        </div>
      </Card>'''
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated IssueDetailsPanel.tsx")
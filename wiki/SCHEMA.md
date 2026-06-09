# Wiki Schema

## Domain
作业票审查知识库 —— 服务于危险化学品企业特殊作业（动火/受限空间/盲板抽堵）的安全合规审查。
核心标准：GB 30871-2022《危险化学品企业特殊作业安全规范》。
关联标准：AQ 3009-2022、AQ 3022-2008、GB/T 13869-2017 等。
审查维度：作业危害辨识、风险控制措施、现场条件与气体分析、审批签字、时效性、人员资质、交叉作业、作业关闭。

## Conventions
- 文件名：小写、连字符、无空格（如 `gb30871-2022-hot-work.md`）
- 每个 Wiki 页面以 YAML frontmatter 开头
- 使用 `[[wikilinks]]` 链接页面（每页至少 2 个出站链接）
- 更新页面时务必更新 `updated` 日期
- 新页面必须添加到 `index.md` 对应分类下
- 每次操作追加到 `log.md`

## Frontmatter
```yaml
---
title: 页面标题
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query
tags: [从标签表选择]
sources: [raw/source-name.md]
# 标准特有字段：
standard_id: GB 30871-2022
standard_type: 国标 | 行标 | 部门规章
status: 现行 | 废止 | 修订
# 审查特有字段：
review_dimension: 作业危害辨识 | 风险控制措施 | 现场条件与气体分析 | 审批签字 | 时效性 | 人员资质 | 交叉作业 | 作业关闭
permit_type: hot_work | confined_space | blind_plate
---
```

## Tag Taxonomy
- 标准类型：国标-GB, 行标-AQ, 部门规章
- 作业类型：动火作业, 受限空间作业, 盲板抽堵作业
- 审查维度：作业危害辨识, 风险控制措施, 现场条件, 气体分析, 审批签字, 时效性, 人员资质, 交叉作业, 作业关闭
- 安全要素：安全措施, 气体检测, 监护人, 审批人, 个体防护, 隔离置换, 盲板管理
- 管理要素：安全管理, 应急救援, 事故调查, 风险评估, 隐患排查

规则：每个标签必须来自本表。需要新标签时先添加到这里再使用。

## Page Thresholds
- **创建页面：** 每个标准/法规创建独立实体页；每种作业类型的核心条款创建独立概念页；每个审查维度创建概念页
- **拆分页面：** 超过 200 行时按子主题拆分并交叉链接
- **不要创建页面：** 标准中的附录表格、格式样本

## 文件分类存放
- `raw/` — 原始法规文档（完整 markdown 转换）
- `entities/` — 具体标准/法规页面（如 gb30871-2022.md）
- `concepts/` — 核心概念页面（审查维度、作业类型要点）
- `comparisons/` — 标准对比分析
- `queries/` — 审查常见问题解答

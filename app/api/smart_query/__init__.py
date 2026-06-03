"""
SmartQuery 智能问数模块
从 SQLAgent-dev 解耦而来，提供 NL2SQL（自然语言转SQL）完整功能

子模块：
- clients:  Vanna 客户端、Embedding 客户端、全局上下文
- config:   系统提示词、配置
- tools:    数据库工具（表信息、SQL执行、语法校验、RAG检索）
- middleware: UI事件注入、选择性打印、调用追踪
- agent:   NL2SQL Agent 创建、后处理训练
"""

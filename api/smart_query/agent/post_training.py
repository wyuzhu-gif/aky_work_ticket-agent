"""
后处理训练模块：负责训练后处理，优化冗余（如LLM实例只创建一次）
使用 Pydantic 结构化输出替代正则解析 JSON

迁移自 SQLAgent-dev: backend/vanna/src/Improve/agent/post_training.py
改动：import 路径从 ..shared 改为 ..clients
"""

import logging
logger = logging.getLogger(__name__)
from typing import List, Any, TypedDict
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


# ==================== Pydantic 结构化输出模型 ====================

class SimilarityEvaluation(BaseModel):
    """相似度评估结果（结构化输出）"""
    most_similar_question: str = Field(
        description="最相似的问题原文，如果没有相似问题则为空字符串"
    )
    similarity_score: float = Field(
        ge=0.0, 
        le=1.0, 
        description="相似度评分 0.0-1.0"
    )
    similarity_analysis: str = Field(
        description="相似度分析：详细解释为什么选择这个相似度评分"
    )


class SQLSelection(BaseModel):
    """SQL选择结果（结构化输出）"""
    selected_sql: str = Field(
        description="完整的 SQL 语句（从列表中选择一个，不要修改）"
    )
    reason: str = Field(
        description="选择理由：简要说明为什么选择这个 SQL"
    )


class ConversationSummary(TypedDict):
    """对话摘要的结构化定义（类型安全）"""
    question: str
    sql_list: List[str]
    execution_result: str
    final_answer: str
    tool_calls: List[dict]


# ==================== 对话摘要提取 ====================

def extract_conversation_summary(messages: List[Any]) -> ConversationSummary:
    """从消息历史中提取关键信息
    
    Args:
        messages: LangChain 消息列表（包含用户消息、AI消息、工具消息）
        
    Returns:
        包含问题、SQL、执行结果的字典
    """
    summary = {
        "question": "",
        "sql_list": [],
        "execution_result": "",
        "final_answer": "",
        "tool_calls": [],
    }
    
    for msg in messages:
        msg_type = getattr(msg, 'type', 'unknown')
        
        if msg_type == 'human' and not summary["question"]:
            summary["question"] = getattr(msg, 'content', '')
        
        if msg_type == 'ai' and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.get('name', '')
                tool_args = tc.get('args', {})
                summary["tool_calls"].append({
                    "tool": tool_name,
                    "args": tool_args
                })
                
                if tool_name == 'execute_sql':
                    sql = tool_args.get('sql', '')
                    if sql and sql not in summary["sql_list"]:
                        summary["sql_list"].append(sql)
        
        if msg_type == 'tool':
            content = getattr(msg, 'content', '')
            if 'SELECT' in content.upper() and len(content) < 1000:
                sql = content.strip()
                if sql not in summary["sql_list"]:
                    summary["sql_list"].append(sql)
            
            if '查询成功' in content or '返回行数' in content:
                summary["execution_result"] = content
        
        if msg_type == 'ai':
            content = getattr(msg, 'content', '')
            if content and not hasattr(msg, 'tool_calls'):
                summary["final_answer"] = content
    
    return summary


class PostTrainingProcessor:
    """后处理训练处理器，负责决策是否将对话加入训练集
    
    优化：复用全局 LLM 实例，避免重复创建
    """

    def __init__(self):
        """初始化处理器（从全局上下文获取 LLM 实例）"""
        from ..clients import get_llm_instance
        
        self.llm = get_llm_instance()
        if self.llm is None:
            raise RuntimeError("LLM 实例未初始化，请先调用 set_llm_instance()")
    
    def decide_and_add_to_training(
        self,
        question: str,
        conversation_history: List[Any],
        vanna_client
    ) -> str:
        """基于对话历史决策是否加入训练集，并执行添加"""
        try:
            summary = extract_conversation_summary(conversation_history)
            
            logger.info("对话摘要：")
            logger.info(f"  问题: {summary['question'][:100]}...")
            logger.info(f"  SQL 数量: {len(summary['sql_list'])}")
            logger.info(f"  工具调用: {len(summary['tool_calls'])} 次")
            logger.info(f"  最终答案: {summary['final_answer'][:100]}...")
            
            # 检索相似问题
            similar_sqls = vanna_client.get_similar_question_sql(question, n_results=5)
            
            if similar_sqls:
                logger.info(f"找到 {len(similar_sqls)} 个相似问题")
            else:
                logger.info("未找到相似问题")
            
            # 评估相似度
            similarity_result = self._evaluate_similarity_structured(
                summary['question'], 
                similar_sqls
            )
            
            most_similar = similarity_result.most_similar_question
            similarity_score = similarity_result.similarity_score
            
            logger.info(f"  最相似问题: {most_similar[:50]}{'...' if len(most_similar) > 50 else ''}")
            logger.info(f"  相似度评分: {similarity_score:.2f}")
            
            # 基于相似度直接决策
            if similarity_score >= 0.85:
                return f"未添加到训练集（相似度过高: {similarity_score:.2f}）"
            
            if '查询成功' not in summary['execution_result']:
                return "未添加到训练集（SQL执行失败）"
            
            if not summary['sql_list']:
                return "未添加到训练集（未找到SQL）"
            
            # 选择最优SQL
            sql_result = self._select_best_sql_structured(
                summary['question'],
                summary['sql_list'],
                summary['execution_result'],
                summary['final_answer']
            )
            
            selected_sql = sql_result.selected_sql
            selection_reason = sql_result.reason
            
            logger.info(f"  选择的SQL: {selected_sql[:80]}{'...' if len(selected_sql) > 80 else ''}")
            logger.info(f"  选择理由: {selection_reason[:80]}...")
            
            # 执行添加
            if selected_sql:
                try:
                    sql_id = vanna_client.train(question=question, sql=selected_sql)
                    
                    if "已存在" in str(sql_id):
                        return f"未添加（数据已存在）\nSQL ID: {sql_id}"
                    else:
                        return f"已成功添加到训练集！\n训练数据ID: {str(sql_id)[:50]}..."
                except Exception as e:
                    return f"添加到训练集失败\n错误信息: {str(e)}"
            else:
                return "未添加到训练集（SQL选择失败）"
                
        except Exception as e:
            return f"训练决策失败\n错误信息: {str(e)}"
    
    def _evaluate_similarity_structured(
        self, 
        question: str, 
        similar_sqls: list
    ) -> SimilarityEvaluation:
        """评估相似度（使用结构化输出）"""
        structured_llm = self.llm.with_structured_output(SimilarityEvaluation)
        
        prompt = f"""
你是一个语义相似度评估专家。请评估用户问题与训练集中已有问题的相似度，并以 JSON 格式返回结果。

**用户问题:**
{question}

**训练集中的相似问题（按向量检索结果排序，共{len(similar_sqls)}个）:**

"""
        
        if similar_sqls:
            for i, pair in enumerate(similar_sqls, 1):
                prompt += f"[{i}] {pair.get('question', 'N/A')}\n"
        else:
            prompt += "（未找到相似问题）\n"
        
        prompt += """

**任务要求:**
请从上述问题中找出与用户问题最相似的那个，并给出相似度评分（0-1）。

**评分标准:**
- 1.0: 完全相同（只是标点、空格等细微差异）
- 0.95-0.99: 语义完全一致，表述略有不同
- 0.85-0.94: 高度相似，核心意图相同，细节略有差异
- 0.70-0.84: 较为相似，属于同类问题但具体查询内容不同
- 0.50-0.69: 部分相似，涉及相同领域但查询目标不同
- < 0.50: 不相似

**重要提示：**
- 如果训练集为空，similarity_score 应为 0
- 必须基于语义相似度，不是关键词匹配
- 相似度评分要严格遵守标准，不要过于宽松
"""
        
        return structured_llm.invoke(prompt)
    
    def _select_best_sql_structured(
        self,
        question: str,
        sql_list: List[str],
        execution_result: str,
        final_answer: str
    ) -> SQLSelection:
        """选择最优SQL（使用结构化输出）"""
        structured_llm = self.llm.with_structured_output(SQLSelection)
        
        prompt = f"""
你是一个 SQL 专家。请从对话历史中提取的 SQL 语句中，选出最重要、最有价值的那个用于加入训练集，并以 JSON 格式返回结果。

**用户问题:**
{question}

**对话中生成的 SQL 语句（共 {len(sql_list)} 个）:**

"""
        
        for i, sql in enumerate(sql_list, 1):
            prompt += f"\n[SQL {i}]\n{sql}\n"
        
        prompt += f"""

**执行结果:**
{execution_result[:500]}

**最终答案:**
{final_answer}

**任务要求:**
请选择一个最适合加入训练集的 SQL 语句。

**选择标准:**
1. 能够正确回答用户问题（执行成功并返回了正确结果）
2. SQL 语句结构清晰、规范
3. 如果有多个 SQL，选择最终使用的那个（通常是最后一个执行成功的）
4. 不要修改 SQL 内容，直接返回原始语句

**重要提示：**
- selected_sql 必须是上面列表中的某一个，完整复制，不要修改
- 如果只有一个 SQL，就选择它
- 如果有多个，选择最终执行成功并给出答案的那个
"""
        
        return structured_llm.invoke(prompt)

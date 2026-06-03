"""
选择性工具打印器（Selective Tool Printer）
用于精准控制特定工具的打印输出，不影响原始事件流

迁移自 SQLAgent-dev: backend/vanna/src/Improve/middleware/selective_tool_printer.py
无改动：纯观察者模式，不依赖 shared 模块
"""

import logging
logger = logging.getLogger(__name__)
import re
from textwrap import shorten
from typing import Set, Optional, Any
from langchain_core.callbacks.base import BaseCallbackHandler


class SelectiveToolPrinter(BaseCallbackHandler):
    """
    选择性工具打印回调
    
    只对指定的工具进行精简打印，其他工具和事件保持静默
    """
    
    def __init__(
        self,
        targets: tuple = ("get_all_tables_info", "get_table_schema"),
        max_chars: int = 1200,
        max_lines: int = 40,
        show_summary: bool = True,
        show_tool_output: bool = True,
        echo_non_targets: bool = False,
    ):
        super().__init__()
        self.targets = set(targets)
        self.max_chars = max_chars
        self.max_lines = max_lines
        self.show_summary = show_summary
        self.show_tool_output = show_tool_output
        self.echo_non_targets = echo_non_targets
        self._current_tool_name = None
    
    def on_tool_start(
        self, 
        serialized: dict, 
        input_str: str, 
        **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name", "unknown")
        self._current_tool_name = name
        
        if name in self.targets or self.echo_non_targets:
            preview = self._truncate_text(input_str, 200, 5)
            logger.info(f"\n[工具调用] {name}")
            if preview:
                logger.info(f"   参数: {preview}")
    
    def on_tool_end(
        self, 
        output: str, 
        **kwargs: Any
    ) -> None:
        if self._current_tool_name not in self.targets:
            self._current_tool_name = None
            return
        
        text = str(output) if output is not None else ""
        if not text:
            self._current_tool_name = None
            return
        
        logger.info(f"\n[{self._current_tool_name}] 返回结果:")
        
        if self.show_summary:
            self._print_summary(text, self._current_tool_name)
        
        if self.show_tool_output:
            body = self._truncate_text(text, self.max_chars, self.max_lines)
            logger.info("\n" + "-" * 60)
            logger.info(body)
            logger.info("-" * 60)
        
        self._current_tool_name = None
    
    def on_tool_error(
        self, 
        error: Exception, 
        **kwargs: Any
    ) -> None:
        error_msg = str(error)[:200]
        logger.error(f"\n[工具错误] {self._current_tool_name or 'unknown'}")
        logger.info(f"   错误信息: {error_msg}...")
        self._current_tool_name = None
    
    def _print_summary(self, text: str, tool_name: str) -> None:
        """打印结构化摘要"""
        tables = re.findall(
            r"CREATE TABLE\s+([`\"]?\[?)([\w\.]+)\1", 
            text, 
            flags=re.IGNORECASE
        )
        table_names = [m[1] for m in tables]
        
        if table_names:
            unique_tables = sorted(set(table_names))
            table_count = len(unique_tables)
            sample_tables = ", ".join(unique_tables[:5])
            if table_count > 5:
                sample_tables += f" ... (共{table_count}张表)"
            logger.info(f"   发现表: {sample_tables}")
        
        table_blocks = len(re.findall(r"^表名\s*:", text, flags=re.MULTILINE))
        if table_blocks:
            logger.info(f"   表清单段落: {table_blocks} 个")
        
        ddl_blocks = text.count("CREATE TABLE")
        if ddl_blocks:
            logger.info(f"   DDL 语句: {ddl_blocks} 个")
        
        col_matches = re.findall(r"列数\s*:\s*(\d+)", text)
        if col_matches:
            total_cols = sum(int(c) for c in col_matches)
            logger.info(f"   总列数: {total_cols}")
        
        if "业务文档说明" in text:
            doc_count = text.count("业务文档说明") or text.count("[文档")
            logger.info(f"   业务文档: {doc_count} 段")
        
        if "历史相似查询" in text:
            sql_count = text.count("[示例") or text.count("SQL:")
            logger.info(f"   历史查询: {sql_count} 个")
    
    def _truncate_text(
        self, 
        text: str, 
        max_chars: int, 
        max_lines: int
    ) -> str:
        if not text:
            return text
        
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["... (输出已截断，共{}行)".format(len(text.splitlines()))]
        text2 = "\n".join(lines)
        
        if len(text2) > max_chars:
            text2 = shorten(
                text2, 
                width=max_chars, 
                placeholder=" ... (内容过长已截断)"
            )
        
        return text2
    
    # 静默其他事件
    def on_llm_start(self, *args, **kwargs) -> None: pass
    def on_llm_end(self, *args, **kwargs) -> None: pass
    def on_llm_new_token(self, *args, **kwargs) -> None: pass
    def on_chain_start(self, *args, **kwargs) -> None: pass
    def on_chain_end(self, *args, **kwargs) -> None: pass
    def on_agent_action(self, *args, **kwargs) -> None: pass
    def on_agent_finish(self, *args, **kwargs) -> None: pass


def create_selective_printer(
    mode: str = "minimal",
    targets: tuple = ("get_all_tables_info", "get_table_schema")
) -> SelectiveToolPrinter:
    """创建选择性打印器（预设模式）"""
    mode_configs = {
        "minimal": {
            "max_chars": 0,
            "max_lines": 0,
            "show_summary": True,
            "show_tool_output": False,
        },
        "compact": {
            "max_chars": 300,
            "max_lines": 10,
            "show_summary": True,
            "show_tool_output": True,
        },
        "detailed": {
            "max_chars": 1000,
            "max_lines": 30,
            "show_summary": True,
            "show_tool_output": True,
        },
    }
    
    config = mode_configs.get(mode, mode_configs["compact"])
    
    return SelectiveToolPrinter(
        targets=targets,
        **config
    )

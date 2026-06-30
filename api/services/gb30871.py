"""
GB 30871-2022 法规文本直接读取模块

不依赖 wiki_search / FTS5 / llm-wiki skill，
直接从 raw/papers 读全文，按章节截取注入 prompt。
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# GB 30871-2022 原文路径
GB30871_PATH = "/home/czys/workspace/llmwiki/raw/papers/GB 30871-2022危险化学品企业特殊作业安全规范.md"

# 作业类型 → 章节号映射
# 对应 GB 30871-2022 的章节结构
PERMIT_TYPE_TO_CHAPTER = {
    "hot_work": "5",        # 动火作业
    "confined_space": "6",  # 受限空间作业
    "blind_plate": "7",     # 盲板抽堵作业
    "high_above": "8",      # 高处作业
    "lifting": "9",         # 吊装作业
    "temp_power": "10",     # 临时用电作业
    "earthwork": "11",      # 动土作业
    "road_closure": "12",   # 断路作业
}

# 缓存全文
_full_text_cache: Optional[str] = None


def _load_full_text() -> str:
    """加载 GB 30871-2022 全文（带缓存）"""
    global _full_text_cache
    if _full_text_cache is not None:
        return _full_text_cache

    if not os.path.exists(GB30871_PATH):
        logger.error("GB 30871 文件不存在: %s", GB30871_PATH)
        return ""

    with open(GB30871_PATH, "r", encoding="utf-8") as f:
        _full_text_cache = f.read()
    logger.info("GB 30871 全文加载成功, %d 字符", len(_full_text_cache))
    return _full_text_cache


def _extract_chapter(full_text: str, chapter_num: str) -> str:
    """
    从全文中提取指定章节内容。
    
    章节标题格式: "# 5 动火作业" / "# 10 临时用电作业"
    提取从 "# {chapter_num} " 开始，到下一个 "# {N} " (N != chapter_num) 结束。
    
    同时包含子章节如 "# 5.1 作业分级"。
    """
    # 匹配 "# 5 动火作业" 或 "# 5." 开头的标题行
    # 用正则找到章节起始位置
    pattern = rf'^# {chapter_num}\s+\S+'
    m = re.search(pattern, full_text, re.MULTILINE)
    if not m:
        logger.warning("章节 %s 未找到", chapter_num)
        return ""

    start = m.start()

    # 找下一个章节标题（不含子章节号）
    # 章节标题有两种: "# 6 受限空间作业" (数字) 或 "# 附录 A" (附录)
    rest = full_text[start + 1:]  # +1 跳过当前 #
    # 匹配 "# 数字 空格 非数字文字" (排除子章节如 "# 5.1") 或 "# 附录"
    next_chapter_pattern = r'^(?:# (\d+)\s+[^\d]|# 附录)'
    all_matches = list(re.finditer(next_chapter_pattern, rest, re.MULTILINE))
    for next_m in all_matches:
        next_num = next_m.group(1)
        if next_num is None or next_num != chapter_num:
            end = start + 1 + next_m.start()
            return full_text[start:end].strip()

    return full_text[start:].strip()


def get_regulation_context(permit_type: str) -> str:
    """
    获取审查所需的法规上下文。
    
    返回:
      - 第 4 章 通用要求 (所有作业类型都需要)
      - 对应作业类型的章节 (如第 5 章动火作业)
    
    如果找不到，返回空字符串。
    """
    full_text = _load_full_text()
    if not full_text:
        return ""

    chapter_num = PERMIT_TYPE_TO_CHAPTER.get(permit_type)
    if not chapter_num:
        logger.warning("未知作业类型: %s", permit_type)
        # 未知类型，只返回通用要求
        ch4 = _extract_chapter(full_text, "4")
        return ch4

    # 提取第4章 + 对应章节
    ch_general = _extract_chapter(full_text, "4")
    ch_specific = _extract_chapter(full_text, chapter_num)

    parts = []
    if ch_general:
        parts.append(ch_general)
    if ch_specific:
        parts.append(ch_specific)

    context = "\n\n".join(parts)
    logger.info(
        "法规上下文: permit_type=%s, 第4章=%d字符, 第%s章=%d字符, 总计=%d字符",
        permit_type, len(ch_general), chapter_num, len(ch_specific), len(context),
    )
    return context


def get_clause_text(clause_num: str) -> Optional[str]:
    """
    从 GB 30871 全文中提取指定条款号的原文。
    
    例如: "5.3.1" → "5.3.1 动火作业前应进行气体分析,要求如下: ..."
    
    支持多级条款号: "5.3.1", "5.2", "4.12" 等。
    """
    full_text = _load_full_text()
    if not full_text:
        return None

    lines = full_text.split("\n")
    captured = []
    started = False

    for line in lines:
        stripped = line.strip().lstrip("#").strip()

        if not started:
            # 匹配条款号开头: "5.3.1 " 或 "5.3.1." 或 "5.3.1、"
            if stripped.startswith(clause_num):
                # 确保后面是空格/点/冒号/顿号/换行
                rest = stripped[len(clause_num):]
                if not rest or rest[0] in " .:：、\t":
                    captured.append(line)
                    started = True
        else:
            # 停在下一个条款号 "# 数字.数字" 或 "# 数字.数字.数字"
            m_next = re.match(
                r'^(?:#\s*)?(\d+(?:\.\d+(?:\.\d+)?))(?:\s+|\.|\:|\u3001)',
                stripped,
            )
            if m_next and m_next.group(1) != clause_num:
                break
            if not stripped:
                captured.append(line)
                continue
            captured.append(line)
            # 单条条款超过 15 行，强制停
            if len(captured) > 15:
                break

    content = "\n".join(captured).strip()
    if content:
        if len(content) > 800:
            content = content[:800] + "..."
        return content

    return None

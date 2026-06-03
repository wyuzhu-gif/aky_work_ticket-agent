"""
Wiki 知识库检索模块

基于 LLM Wiki + SQLite FTS5(jieba分词) 实现中文法规知识检索，
替代 Milvus + Jina Embedding 的向量检索方案。

功能：
  - search(): 通用关键词检索
  - search_for_permit_review(): 按票种检索合规审查相关页面
  - search_for_document_review(): 文档审查上下文检索
  - get_page(): 读取指定 wiki 页面全文
  - get_permit_review_context(): 合规审查专用，返回完整的审查法规上下文
  - rebuild_index(): 重建 FTS5 索引
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# jieba lazy-load (only needed for indexing / query segmentation)
# ---------------------------------------------------------------------------
_jieba = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba
            jieba.setLogLevel(20)
            _jieba = jieba
        except ImportError:
            raise ImportError(
                "jieba is required for Wiki search. "
                "Install with: pip install jieba"
            )
    return _jieba


def _segment(text: str) -> str:
    """用 jieba 分词，返回空格分隔的词序列（供 FTS5 索引/查询）"""
    return " ".join(_get_jieba().cut(text))


# ---------------------------------------------------------------------------
# 票种 → wiki 页面映射（硬编码的检索策略，确保必查项不遗漏）
# ---------------------------------------------------------------------------
PERMIT_TYPE_PAGES = {
    "hot_work": {
        "entity": "entities/gb30871-2022-hot-work.md",
        "concepts": [
            "concepts/动火作业安全措施.md",
            "concepts/气体检测要求.md",
            "concepts/动火作业审批要求.md",
            "concepts/管道隔离要求.md",
        ],
        "general": "entities/gb30871-2022-general.md",
    },
    "confined_space": {
        "entity": "entities/gb30871-2022-confined-space.md",
        "concepts": [
            "concepts/受限空间安全措施.md",
            "concepts/气体检测要求.md",
            "concepts/受限空间作业审批要求.md",
            "concepts/管道隔离要求.md",
        ],
        "general": "entities/gb30871-2022-general.md",
    },
    "blind_plate": {
        "entity": "entities/gb30871-2022-blind-plate.md",
        "concepts": [
            "concepts/盲板抽堵安全措施.md",
            "concepts/盲板抽堵审批要求.md",
            "concepts/管道隔离要求.md",
        ],
        "general": "entities/gb30871-2022-general.md",
    },
}


class WikiSearch:
    """Wiki 知识库检索器"""

    def __init__(self, wiki_path: str, search_limit: int = 3):
        self.wiki_path = Path(wiki_path).resolve()
        self.db_path = self.wiki_path / "semantic_index.sqlite"
        self.search_limit = search_limit

        if not self.db_path.exists():
            logger.warning(
                "Wiki index not found at %s. Run rebuild_index() first.",
                self.db_path,
            )

    # ------------------------------------------------------------------
    # Low-level search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: Optional[int] = None,
        page_type: Optional[str] = None,
    ) -> list[dict]:
        """
        FTS5 全文检索。

        Args:
            query: 自然语言查询（中文）
            limit: 返回结果数（默认用 wiki_search_limit）
            page_type: 过滤页面类型 ('entity'|'concept'|'comparison')

        Returns:
            [{"filepath": str, "title": str, "page_type": str, "snippet": str}]
        """
        if not self.db_path.exists():
            logger.error("Wiki index not found: %s", self.db_path)
            return []

        limit = limit or self.search_limit

        # Segment query for FTS5
        seg_q = _segment(query)
        # Use OR for broad recall (Chinese terms are often multi-word)
        fts_query = " OR ".join(seg_q.split())

        conn = sqlite3.connect(str(self.db_path))
        try:
            # FTS5 virtual table: search for segmented terms
            rows = conn.execute(
                """
                SELECT filepath, snippet(pages, 1, '>>>', '<<<', '...', 15) as snippet
                FROM pages
                WHERE pages MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit * 2),  # fetch extra for filtering
            ).fetchall()

            output = []
            for filepath, snippet in rows:
                # Get metadata from page_meta (real table, supports any query)
                meta = conn.execute(
                    "SELECT title, page_type FROM page_meta WHERE filepath=?",
                    (filepath,),
                ).fetchone()
                if not meta:
                    continue
                orig_title, ptype = meta
                if page_type and ptype != page_type:
                    continue
                output.append(
                    {
                        "filepath": filepath,
                        "title": orig_title,
                        "page_type": ptype,
                        "snippet": snippet.replace(">>>", "").replace("<<<", ""),
                    }
                )
                if len(output) >= limit:
                    break

            return output
        except Exception as e:
            logger.error("Wiki search error: %s", e)
            return []
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # High-level: read page content
    # ------------------------------------------------------------------

    def get_page(self, relative_path: str) -> Optional[str]:
        """读取 wiki 页面全文（去除 frontmatter）"""
        full_path = self.wiki_path / relative_path
        if not full_path.exists():
            logger.warning("Wiki page not found: %s", full_path)
            return None

        text = full_path.read_text(encoding="utf-8")

        # Strip YAML frontmatter
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                return text[end + 3 :].strip()

        return text

    def get_page_raw(self, relative_path: str) -> Optional[str]:
        """读取 wiki 页面原文（含 frontmatter）"""
        full_path = self.wiki_path / relative_path
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # High-level: permit review context
    # ------------------------------------------------------------------

    def get_permit_review_context(
        self,
        permit_type: str,
        max_chars: int = 6000,
    ) -> str:
        """
        合规审查专用：按票种返回完整的审查法规上下文。

        检索策略（写在 purpose.md 中，此处硬编码执行）：
          1. 读取该票种的实体页（对应法规章节原文）
          2. 读取关联概念页（安全措施、审批要求等）
          3. 读取通用要求章节
          4. 总长度控制在 max_chars 以内

        Args:
            permit_type: 'hot_work' | 'confined_space' | 'blind_plate'
            max_chars: 最大返回字符数

        Returns:
            拼接的法规上下文文本
        """
        pages_config = PERMIT_TYPE_PAGES.get(permit_type)
        if not pages_config:
            logger.warning("Unknown permit_type: %s", permit_type)
            # Fallback: search by keyword
            return self._search_fallback(permit_type, max_chars)

        sections = []

        # 1. Entity page (regulation chapter)
        entity_content = self.get_page(pages_config["entity"])
        if entity_content:
            sections.append(f"## 法规原文\n\n{entity_content}")

        # 2. Concept pages (safety measures, approval requirements, etc.)
        for concept_path in pages_config["concepts"]:
            content = self.get_page(concept_path)
            if content:
                title = Path(concept_path).stem
                sections.append(f"## {title}\n\n{content}")

        # 3. General requirements
        general_content = self.get_page(pages_config["general"])
        if general_content:
            sections.append(f"## 通用要求\n\n{general_content}")

        # Combine and truncate
        full_context = "\n\n---\n\n".join(sections)
        if len(full_context) > max_chars:
            full_context = full_context[:max_chars] + "\n\n[...已截断]"

        return full_context

    def _search_fallback(self, permit_type: str, max_chars: int) -> str:
        """未知票种时，用关键词检索作为 fallback"""
        type_keywords = {
            "hot_work": "动火作业 安全措施 审批 气体检测",
            "confined_space": "受限空间 安全措施 气体检测 审批",
            "blind_plate": "盲板抽堵 安全措施 审批 管道隔离",
        }
        query = type_keywords.get(permit_type, permit_type)
        results = self.search(query, limit=5)

        sections = []
        for r in results:
            content = self.get_page(r["filepath"])
            if content:
                sections.append(f"## {r['title']}\n\n{content}")

        if not sections:
            return ""

        full_context = "\n\n---\n\n".join(sections)
        if len(full_context) > max_chars:
            full_context = full_context[:max_chars] + "\n\n[...已截断]"
        return full_context

    # ------------------------------------------------------------------
    # High-level: document review context
    # ------------------------------------------------------------------

    def get_document_review_context(
        self,
        doc_type: str = "",
        keywords: str = "",
        max_chars: int = 4000,
    ) -> str:
        """
        文档审查上下文检索。

        Args:
            doc_type: 文档类型关键词
            keywords: 额外检索关键词
            max_chars: 最大返回字符数
        """
        query_parts = [doc_type, keywords, "安全措施 审批要求 合规"] 
        query = " ".join(p for p in query_parts if p)

        results = self.search(query, limit=5)
        sections = []
        for r in results:
            content = self.get_page(r["filepath"])
            if content:
                sections.append(f"## {r['title']}\n\n{content}")

        if not sections:
            return ""

        full_context = "\n\n---\n\n".join(sections)
        if len(full_context) > max_chars:
            full_context = full_context[:max_chars] + "\n\n[...已截断]"
        return full_context

    # ------------------------------------------------------------------
    # Index rebuild
    # ------------------------------------------------------------------

    def rebuild_index(self) -> dict:
        """
        重建 FTS5 索引（扫描 wiki 目录下所有 .md 文件）。
        应在 wiki 内容更新后调用。
        """
        import glob as glob_mod

        if self.db_path.exists():
            os.remove(str(self.db_path))

        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()

        c.execute(
            """CREATE VIRTUAL TABLE pages USING fts5(
                title, content, filepath, tags, permit_type, page_type,
                tokenize='simple'
            )"""
        )
        c.execute(
            """CREATE VIRTUAL TABLE sections USING fts5(
                heading, body, filepath, page_title,
                tokenize='simple'
            )"""
        )
        c.execute(
            """CREATE TABLE page_meta (
                filepath TEXT PRIMARY KEY, title TEXT, page_type TEXT,
                tags TEXT, permit_type TEXT, standard_id TEXT,
                line_count INTEGER, char_count INTEGER
            )"""
        )

        count = 0
        for subdir in ["entities", "concepts", "comparisons", "queries"]:
            for fpath in sorted(
                glob_mod.glob(str(self.wiki_path / subdir / "*.md"))
            ):
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()

                rel_path = os.path.relpath(fpath, str(self.wiki_path))
                title = ""
                page_type = subdir.rstrip("s")
                tags = ""
                permit_type = ""
                standard_id = ""

                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        fm = text[3:end].strip()
                        for line in fm.split("\n"):
                            if line.startswith("title:"):
                                title = (
                                    line.split(":", 1)[1]
                                    .strip()
                                    .strip("'")
                                    .strip('"')
                                )
                            elif line.startswith("tags:"):
                                tags = line.split(":", 1)[1].strip()
                            elif line.startswith("permit_type:"):
                                permit_type = line.split(":", 1)[1].strip()
                            elif line.startswith("standard_id:"):
                                standard_id = line.split(":", 1)[1].strip()

                content = text
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        content = text[end + 3 :].strip()

                seg_title = _segment(title)
                seg_content = _segment(content)
                seg_tags = _segment(tags)
                seg_permit = _segment(permit_type)
                seg_type = _segment(page_type)

                c.execute(
                    "INSERT INTO pages VALUES (?,?,?,?,?,?)",
                    (seg_title, seg_content, rel_path, seg_tags, seg_permit, seg_type),
                )

                # Sections
                current_heading = title
                seg_heading = _segment(title)
                current_body = []
                for line in content.split("\n"):
                    if line.startswith("## "):
                        if current_body:
                            body_text = "\n".join(current_body).strip()
                            if body_text:
                                c.execute(
                                    "INSERT INTO sections VALUES (?,?,?,?)",
                                    (seg_heading, _segment(body_text), rel_path, seg_title),
                                )
                        current_heading = line.strip("# ").strip()
                        seg_heading = _segment(current_heading)
                        current_body = []
                    else:
                        current_body.append(line)
                if current_body:
                    body_text = "\n".join(current_body).strip()
                    if body_text:
                        c.execute(
                            "INSERT INTO sections VALUES (?,?,?,?)",
                            (seg_heading, _segment(body_text), rel_path, seg_title),
                        )

                c.execute(
                    "INSERT INTO page_meta VALUES (?,?,?,?,?,?,?,?)",
                    (
                        rel_path, title, page_type, tags, permit_type, standard_id,
                        len(text.split("\n")), len(text),
                    ),
                )
                count += 1

        conn.commit()
        pc = c.execute("SELECT count(*) FROM pages").fetchone()[0]
        sc = c.execute("SELECT count(*) FROM sections").fetchone()[0]
        conn.close()

        logger.info("Wiki index rebuilt: %d files, %d pages, %d sections", count, pc, sc)
        return {"files": count, "pages": pc, "sections": sc}


# ---------------------------------------------------------------------------
# Singleton (lazy-init)
# ---------------------------------------------------------------------------
_wiki_search: Optional[WikiSearch] = None


def get_wiki_search(wiki_path: Optional[str] = None, search_limit: Optional[int] = None) -> WikiSearch:
    """获取 WikiSearch 单例"""
    global _wiki_search
    if _wiki_search is None:
        from config.config import settings

        _wiki_search = WikiSearch(
            wiki_path=wiki_path or settings.wiki_path,
            search_limit=search_limit or settings.wiki_search_limit,
        )
    return _wiki_search

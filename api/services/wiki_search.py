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
# 票种 → 检索关键词映射（新 wiki 库适配版，无硬编码文件路径）
# ---------------------------------------------------------------------------
PERMIT_TYPE_KEYWORDS = {
    "hot_work": [
        "动火作业 安全措施 审批 气体检测",
        "GB 30871 动火",
        "动火作业许可证",
    ],
    "confined_space": [
        "受限空间 安全措施 气体检测 审批",
        "GB 30871 受限空间",
        "受限空间作业许可证",
    ],
    "blind_plate": [
        "盲板抽堵 安全措施 审批 管道隔离",
        "GB 30871 盲板",
        "盲板抽堵作业许可证",
    ],
}

# 兼容旧 PERMIT_TYPE_PAGES 接口（如有其他代码引用）
PERMIT_TYPE_PAGES = {
    pt: {"entity": None, "concepts": [], "general": None}
    for pt in PERMIT_TYPE_KEYWORDS
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
        搜索 Wiki（基于 LIKE 模糊匹配，兼容 rebuild_index.py 建的 sections 表）。

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
        # 多取一些以备过滤
        fetch_limit = limit * 3

        conn = sqlite3.connect(str(self.db_path))
        try:
            # 检测表结构
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            if 'sections' in tables and 'pages' not in tables:
                # rebuild_index.py schema: sections(path, title, content)
                # 用 jieba 分词后 OR 匹配（任一词命中即可），提高召回率
                jieba_lib = _get_jieba()
                # 分词 + 去停用词 + 去标点 + 去单字
                stopwords = {'的', '了', '是', '在', '和', '与', '或', '及', '等', '为',
                             '我', '你', '他', '她', '它', '们', '这', '那', '个', '中',
                             '上', '下', '不', '有', '没', '对', '到', '把', '被', '从',
                             '请', '问', '一下', '告诉', '说', '要', '能', '会', '可以'}
                raw_terms = [w.strip() for w in jieba_lib.cut(query) if w.strip()]
                terms = [t for t in raw_terms if t not in stopwords and len(t) > 1]
                # 至少一个 term；terms 为空时退回整句匹配
                if not terms:
                    terms = [query]

                # 构造动态 WHERE: (title LIKE ? OR content LIKE ?) 对每个 term
                where_clauses = []
                params = []
                for t in terms:
                    like_t = f"%{t}%"
                    where_clauses.append("(title LIKE ? OR content LIKE ?)")
                    params.extend([like_t, like_t])
                where_sql = " OR ".join(where_clauses)

                # ORDER BY: 命中 term 数越多越靠前，title 命中权重更高
                # title 命中计 2 分, content 命中计 1 分
                hit_expr = " + ".join(
                    f"(CASE WHEN title LIKE ? THEN 2 ELSE 0 END + CASE WHEN content LIKE ? THEN 1 ELSE 0 END)"
                    for _ in terms
                )
                hit_params = []
                for t in terms:
                    like_t = f"%{t}%"
                    hit_params.extend([like_t, like_t])

                sql = f"""
                    SELECT path, title, content,
                           ({hit_expr}) AS hit_count
                    FROM sections
                    WHERE {where_sql}
                    ORDER BY hit_count DESC, length(title) ASC
                    LIMIT ?
                """
                rows = conn.execute(sql, (*hit_params, *params, fetch_limit)).fetchall()

                output = []
                for row in rows:
                    filepath, title, content, hit_count = row
                    # 推断 page_type（从路径）
                    rel = filepath
                    if "/entities/" in rel:
                        ptype = "entity"
                    elif "/concepts/" in rel:
                        ptype = "concept"
                    elif "/comparisons/" in rel:
                        ptype = "comparison"
                    elif "/queries/" in rel:
                        ptype = "query"
                    elif "/raw/" in rel:
                        ptype = "raw"
                    else:
                        ptype = "other"

                    if page_type and ptype != page_type:
                        continue

                    # snippet: 找到第一个 term 出现的位置，取前后字符
                    snippet = ""
                    if content:
                        first_idx = -1
                        first_term = ""
                        for t in terms:
                            idx = content.find(t)
                            if idx >= 0 and (first_idx < 0 or idx < first_idx):
                                first_idx = idx
                                first_term = t
                        if first_idx >= 0:
                            start = max(0, first_idx - 30)
                            end = min(len(content), first_idx + 60)
                            snippet = ("..." if start > 0 else "") + \
                                content[start:end].replace("\n", " ") + \
                                ("..." if end < len(content) else "")
                        else:
                            snippet = content[:80].replace("\n", " ") + "..."

                    # 相对路径
                    try:
                        rel_path = str(Path(filepath).relative_to(self.wiki_path))
                    except ValueError:
                        rel_path = filepath

                    output.append({
                        "filepath": rel_path,
                        "title": title or Path(filepath).stem,
                        "page_type": ptype,
                        "snippet": snippet,
                    })
                    if len(output) >= limit:
                        break
                return output

            # 旧 FTS5 schema（pages + page_meta）
            seg_q = _segment(query)
            fts_query = " OR ".join(seg_q.split())
            rows = conn.execute(
                """
                SELECT filepath, snippet(pages, 1, '>>>', '<<<', '...', 15) as snippet
                FROM pages
                WHERE pages MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit * 2),
            ).fetchall()

            output = []
            for filepath, snippet in rows:
                meta = conn.execute(
                    "SELECT title, page_type FROM page_meta WHERE filepath=?",
                    (filepath,),
                ).fetchone()
                if not meta:
                    continue
                orig_title, ptype = meta
                if page_type and ptype != page_type:
                    continue
                output.append({
                    "filepath": filepath,
                    "title": orig_title,
                    "page_type": ptype,
                    "snippet": snippet.replace(">>>", "").replace("<<<", ""),
                })
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
        """读取 wiki 页面全文（去除 frontmatter）。同时支持相对路径和绝对路径。"""
        # 兼容绝对路径（rebuild_index.py 存的）
        if Path(relative_path).is_absolute():
            full_path = Path(relative_path)
        else:
            full_path = self.wiki_path / relative_path
        if not full_path.exists():
            logger.warning("Wiki page not found: %s", full_path)
            return None

        text = full_path.read_text(encoding="utf-8")

        # Strip YAML frontmatter
        if text.startswith("---"):
            import re
            text = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.DOTALL)

        return text

    def get_clause_content(self, clause_num: str, wiki_path: str = None) -> Optional[str]:
        """
        从 wiki 抽取具体条款的内容 (如 "5.4.1" -> "5.4.1 特级动火作业应符合 5.2、5.3 的规定。")
        用于审查结果中给用户看条款原文, 让用户自己核对

        Fallback 策略:
        1. 先查 wiki_path (默认 entities/)
        2. 如果找不到或为空, 自动尝试 raw/papers/
        """
        import re

        # 构建候选路径列表
        if wiki_path is None:
            wiki_path = "entities/GB 30871-2022危险化学品企业特殊作业安全规范.md"

        # 主路径 + fallback 路径
        candidate_paths = [wiki_path]
        if wiki_path.startswith("entities/"):
            fallback_path = wiki_path.replace("entities/", "raw/papers/")
            candidate_paths.append(fallback_path)

        # 尝试每个路径
        for path in candidate_paths:
            full = self.get_page(path)
            if not full:
                continue

            # 找 "5.4.1 ..." 这一行起, 到下一个 "数字.数字" 条款号 (或 "## 数字" 标题) 止
            # 例: 5.4.1 ... 5.4.2 ... 5.5.1 ... 6.1 ...
            # 多种格式: 5.4.1 / 5.4.1. / 5.4.1 xxx / # 5.4.1 xxx
            lines = full.split('\n')
            captured = []
            started = False
            for line in lines:
                stripped = line.strip().lstrip('#').strip()  # 去 # 标题符
                # 行首是 clause_num + 空格/点/冒号
                if not started:
                    if stripped.startswith(clause_num) and (len(stripped) == len(clause_num) or stripped[len(clause_num)] in ' .:：、\t'):
                        captured.append(line)
                        started = True
                else:
                    # 停在下个 "数字.数字" 条款号 或 "## 数字" 标题
                    m_next = re.match(r'^(?:#\s*)?(\d+(?:\.\d+(?:\.\d+)?))(?:\s+|\.|\:|\u3001)', stripped)
                    if m_next and m_next.group(1) != clause_num:
                        break
                    # 跳过空行
                    if not stripped:
                        captured.append(line)
                        continue
                    captured.append(line)
                    # 单条条款超过 10 行, 强制停
                    if len(captured) > 10:
                        break

            content = '\n'.join(captured).strip()
            if content:
                if len(content) > 500:
                    content = content[:500] + "..."
                return content

        # 所有路径都找不到
        return None

    # ------------------------------------------------------------------
    # High-level: permit review context
    # ------------------------------------------------------------------

    def get_permit_review_context(
        self,
        permit_type: str,
        max_chars: int = 30000,
    ) -> str:
        """
        合规审查专用：按票种从新 wiki 库检索相关文档，拼接成 LLM 上下文。

        检索策略（适配新 wiki 库，无硬编码文件路径）：
          1. 用 PERMIT_TYPE_KEYWORDS 里该票种的多组关键词分别 search
          2. 去重合并结果
          3. 优先保留 GB 30871 文档
          4. 逐个 get_page 读全文，拼接成 context
          5. 总长度控制在 max_chars 以内

        Args:
            permit_type: 'hot_work' | 'confined_space' | 'blind_plate'
            max_chars: 最大返回字符数

        Returns:
            拼接的法规上下文文本
        """
        queries = PERMIT_TYPE_KEYWORDS.get(permit_type)
        if not queries:
            logger.warning("Unknown permit_type: %s, falling back to generic search", permit_type)
            queries = [f"{permit_type} 安全措施 审批"]

        # 多组 query 去重收集 filepath
        seen_paths = set()
        results = []
        for q in queries:
            hits = self.search(q, limit=5)
            for r in hits:
                fp = r["filepath"]
                if fp not in seen_paths:
                    seen_paths.add(fp)
                    results.append(r)

        # 优先把 GB 30871 排到前面（最相关）
        def priority(r):
            fp = r.get("filepath", "")
            title = r.get("title", "")
            if "30871" in fp or "30871" in title:
                return 0
            if "特殊作业" in title or "动火" in title or "受限空间" in title or "盲板" in title:
                return 1
            return 2
        results.sort(key=priority)

        sections = []
        # 关键设计: 跳过"前言/目录", 直接读具体条款章节
        # 之前 800 字符只装下"目录", LLM 看不到任何条款, 导致编造"第 X.X 条"
        # 现在: 对每个文档, 找到第一个 "## 5" 或 "## 4.6" 这种章节标题, 从那里开始读
        MAX_DOCS = 3
        PER_DOC_CHARS = 6000

        for r in results[:MAX_DOCS]:
            content = self.get_page(r["filepath"])  # 全文
            if content:
                # 跳过"前言/目录"段 (GB 30871 用一级 # 标题)
                # 找第一个包含数字章节号的标题行, 从那里开始
                # 例如: "# 4 通用要求" / "# 5 动火作业"
                import re
                # 找第一个 "# 数字" 的标题位置 (不是 # 前言/目次)
                m = re.search(r'^# \d+\s+\S+', content, re.M)
                if m:
                    content = content[m.start():]
                # 单文档截断
                if len(content) > PER_DOC_CHARS:
                    content = content[:PER_DOC_CHARS] + "\n\n[...文档已截断]"
                title = r.get("title") or Path(r["filepath"]).stem
                fp = r["filepath"]
                sections.append(f"## {title}（{fp}）\n\n{content}")

        if not sections:
            logger.warning(
                f"[PERMIT_REVIEW] permit_type={permit_type} 在新 wiki 库 0 条结果, "
                f"queries={queries}, 索引库={self.db_path}"
            )
            return ""

        # 拼接 + 截断
        full_context = "\n\n---\n\n".join(sections)
        truncated = len(full_context) > max_chars
        if truncated:
            full_context = full_context[:max_chars] + "\n\n[...已截断]"

        logger.info(
            f"[PERMIT_REVIEW] permit_type={permit_type} 用 {len(queries)} 组 query 搜到 "
            f"{len(sections)} 个文档, 总字符={len(full_context)}{'(已截断)' if truncated else ''}"
        )
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

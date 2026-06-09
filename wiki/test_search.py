
import sqlite3, os, sys
try:
    import jieba
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'jieba', '-q'])
    import jieba
jieba.setLogLevel(20)

wiki_dir = "/Users/wyz/workspace/aky_work_ticket/ai-document-review/wiki"
conn = sqlite3.connect(os.path.join(wiki_dir, 'semantic_index.sqlite'))
c = conn.cursor()

def segment(text):
    return ' '.join(jieba.cut(text))

test_queries = [
    "动火作业 气体分析 时效",
    "受限空间 氧含量 有毒气体",
    "盲板 抽堵 一票一块",
    "动火审批 签字 特级",
    "监护人 专职",
    "管道隔离 水封",
    "防爆 防静电",
    "作业票 有效期 超期",
]

for query in test_queries:
    seg_q = segment(query)
    # FTS5 needs AND logic by default, use OR for broader recall
    fts_query = ' OR '.join(seg_q.split())
    
    print(f"\n{'='*50}")
    print(f"查询: {query}")
    print(f"分词: {seg_q}")
    print(f"FTS5: {fts_query}")
    print('-'*50)
    
    try:
        results = c.execute("""
            SELECT title, filepath, snippet(pages, 1, '>>>', '<<<', '...', 15) as snippet
            FROM pages WHERE pages MATCH ?
            ORDER BY rank LIMIT 3
        """, (fts_query,)).fetchall()
        
        for i, (title, fpath, snippet) in enumerate(results, 1):
            # Get original title from page_meta
            meta = c.execute("SELECT title FROM page_meta WHERE filepath=?", (fpath,)).fetchone()
            orig_title = meta[0] if meta else title
            snippet_clean = snippet.replace('\n', ' ')[:100]
            print(f"  [{i}] {orig_title} ({fpath})")
            print(f"      {snippet_clean}")
    except Exception as e:
        print(f"  ERROR: {e}")

conn.close()

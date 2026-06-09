
import sqlite3, os, glob, sys

# Install jieba if needed
try:
    import jieba
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'jieba', '-q'])
    import jieba

jieba.setLogLevel(20)  # suppress verbose logging

wiki_dir = "/Users/wyz/workspace/aky_work_ticket/ai-document-review/wiki"
db_path = os.path.join(wiki_dir, 'semantic_index.sqlite')
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""CREATE VIRTUAL TABLE pages USING fts5(
    title, content, filepath, tags, permit_type, page_type,
    tokenize='unicode61'
)""")

c.execute("""CREATE VIRTUAL TABLE sections USING fts5(
    heading, body, filepath, page_title,
    tokenize='unicode61'
)""")

c.execute("""CREATE TABLE page_meta (
    filepath TEXT PRIMARY KEY, title TEXT, page_type TEXT,
    tags TEXT, permit_type TEXT, standard_id TEXT,
    line_count INTEGER, char_count INTEGER
)""")

def segment(text):
    return ' '.join(jieba.cut(text))

count = 0
for subdir in ['entities', 'concepts', 'comparisons', 'queries']:
    for fpath in sorted(glob.glob(os.path.join(wiki_dir, subdir, '*.md'))):
        with open(fpath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        title, page_type, tags, permit_type, standard_id = '', subdir.rstrip('s'), '', '', ''
        
        if text.startswith('---'):
            end = text.find('---', 3)
            if end > 0:
                fm = text[3:end].strip()
                for line in fm.split('\n'):
                    if line.startswith('title:'):
                        title = line.split(':', 1)[1].strip().strip("'").strip('"')
                    elif line.startswith('tags:'):
                        tags = line.split(':', 1)[1].strip()
                    elif line.startswith('permit_type:'):
                        permit_type = line.split(':', 1)[1].strip()
                    elif line.startswith('standard_id:'):
                        standard_id = line.split(':', 1)[1].strip()
        
        content = text
        if text.startswith('---'):
            end = text.find('---', 3)
            if end > 0:
                content = text[end+3:].strip()
        
        seg_title = segment(title)
        seg_content = segment(content)
        seg_tags = segment(tags)
        seg_permit = segment(permit_type)
        seg_type = segment(page_type)
        
        c.execute('INSERT INTO pages VALUES (?,?,?,?,?,?)',
                  (seg_title, seg_content, fpath, seg_tags, seg_permit, seg_type))
        
        current_heading = title
        seg_heading = segment(title)
        current_body = []
        for line in content.split('\n'):
            if line.startswith('## '):
                if current_body:
                    body_text = '\n'.join(current_body).strip()
                    if body_text:
                        c.execute('INSERT INTO sections VALUES (?,?,?,?)',
                                  (seg_heading, segment(body_text), fpath, seg_title))
                current_heading = line.strip('# ').strip()
                seg_heading = segment(current_heading)
                current_body = []
            else:
                current_body.append(line)
        if current_body:
            body_text = '\n'.join(current_body).strip()
            if body_text:
                c.execute('INSERT INTO sections VALUES (?,?,?,?)',
                          (seg_heading, segment(body_text), fpath, seg_title))
        
        c.execute('INSERT INTO page_meta VALUES (?,?,?,?,?,?,?,?)',
                  (fpath, title, page_type, tags, permit_type, standard_id,
                   len(text.split('\n')), len(text)))
        count += 1
        print(f'  {os.path.basename(fpath)} -> {title}')

conn.commit()
pc = c.execute("SELECT count(*) FROM pages").fetchone()[0]
sc = c.execute("SELECT count(*) FROM sections").fetchone()[0]
conn.close()
print(f'\nDone: {count} files, {pc} pages, {sc} sections')

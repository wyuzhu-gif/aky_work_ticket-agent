"""
Smoke tests - 系统基本功能验证
运行: ./venv/bin/python -m pytest tests/ -v
或:  ./venv/bin/python tests/test_smoke.py
"""
import sys
import os

# 把项目根 + api 加到 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_DIR = os.path.join(ROOT, 'api')
for p in [ROOT, API_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx

API_BASE = os.environ.get('API_BASE', 'http://127.0.0.1:5100')

# pytest 是可选的 (smoke test 主要用 main() 直接跑)
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


# =============================================================================
# 1. 5100 健康
# =============================================================================
def test_api_health():
    """后端 /api/health 返回 204"""
    r = httpx.get(f'{API_BASE}/api/health', timeout=5)
    assert r.status_code == 204, f'健康检查失败: {r.status_code}'


# =============================================================================
# 2. 前端静态文件可访问
# =============================================================================
def test_frontend_static():
    """前端 www/ 静态文件可访问"""
    r = httpx.get(API_BASE, timeout=5)
    assert r.status_code == 200, f'前端不可访问: {r.status_code}'
    # 应该返回 HTML
    assert 'text/html' in r.headers.get('content-type', ''), '前端不是 HTML'


# =============================================================================
# 3. 智能问数创建会话
# =============================================================================
def test_chat_session_create():
    """POST /api/v1/chat/sessions 成功创建"""
    # 看 routers/chat.py 实际接受什么 body
    r = httpx.post(f'{API_BASE}/api/v1/chat/sessions', json={}, timeout=5)
    if r.status_code == 422:
        # 试着不传 body
        r = httpx.post(f'{API_BASE}/api/v1/chat/sessions', timeout=5)
    assert r.status_code == 200, f'会话创建失败: {r.status_code} {r.text[:200]}'
    data = r.json()
    # 响应可能是 {'data': {...}} 或直接的 {...}
    payload = data.get('data', data) if isinstance(data, dict) else data
    assert 'id' in payload or 'session_id' in payload, f'响应缺 id/session_id: {data}'


# =============================================================================
# 4. MySQL 连接
# =============================================================================
def test_mysql_connection():
    """MySQL 8.0 可达且 7 张表存在"""
    import pymysql
    from config.config import settings
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_database,
        charset="utf8mb4",
        connect_timeout=5,
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = DATABASE() ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    conn.close()

    expected = {
        'hot_work_permits', 'confined_space_permits', 'permit_blind_plate',
        'hot_work_gas_analysis', 'confined_space_gas_analysis',
        'work_safety_checks', 'safety_check_items',
    }
    missing = expected - set(tables)
    assert not missing, f'MySQL 缺表: {missing}'


# =============================================================================
# 5. Wiki 知识库文件存在
# =============================================================================
def test_wiki_files():
    """wiki/ 知识库文件存在"""
    wiki = os.path.join(ROOT, 'wiki')
    assert os.path.isdir(wiki), f'wiki 目录不存在: {wiki}'

    entities = os.path.join(wiki, 'entities')
    assert os.path.isdir(entities), f'wiki/entities 目录不存在'

    # 至少有 GB 30871 主实体页
    main = os.path.join(entities, 'gb30871-2022.md')
    assert os.path.isfile(main), f'GB 30871 主实体页缺失: {main}'


# =============================================================================
# 6. Milvus 训练数据存在
# =============================================================================
def test_milvus_training_data():
    """Milvus vannaddl 训练数据存在"""
    try:
        from pymilvus import MilvusClient
    except ImportError:
        if HAS_PYTEST: pytest.skip('pymilvus 未安装')
        else: raise

    from config.config import settings
    mc = MilvusClient(uri=settings.sq_milvus_uri)

    try:
        info = mc.get_collection_stats('vannaddl')
        n = info.get('row_count', 0)
        assert n > 0, f'vannaddl 无数据 (rows={n})'
    finally:
        pass  # pymilvus Lite 不用 close


# =============================================================================
# main (直接跑, 不依赖 pytest)
# =============================================================================
def _run_all():
    """不用 pytest 时逐个跑"""
    tests = [
        ('test_api_health', test_api_health),
        ('test_frontend_static', test_frontend_static),
        ('test_chat_session_create', test_chat_session_create),
        ('test_mysql_connection', test_mysql_connection),
        ('test_wiki_files', test_wiki_files),
        ('test_milvus_training_data', test_milvus_training_data),
    ]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f'  ✓ {name}')
            passed += 1
        except AssertionError as e:
            print(f'  ✗ {name}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ! {name}: {type(e).__name__}: {e}')
            failed += 1
    print(f'\n  结果: {passed} passed, {failed} failed')
    return failed == 0


if __name__ == '__main__' or True:
    # 直接跑 (pytest 没装也 OK)
    print('=== Smoke Tests ===\n')
    ok = _run_all()
    sys.exit(0 if ok else 1)

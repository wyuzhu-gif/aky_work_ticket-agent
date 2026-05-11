"""
test_review_api.py
测试作业票审核系统的上传审核接口
用法: python test_review_api.py <pdf_or_image_path>
"""
import sys
import json
import requests

# ===== 配置 =====
BASE_URL = "http://10.8.0.100:38021"
AUTH_TOKEN = ""

HEADERS = {}
if AUTH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {AUTH_TOKEN}"


def _print_issue(issue: dict, index: int):
    """格式化打印单条审核问题"""
    risk = issue.get("risk_level", "?")
    text = issue.get("text", "")
    print(f"  {index}. [{risk}] {text}", flush=True)
    loc = issue.get("location", {})
    if loc:
        src = loc.get("source_sentence", "")
        if src:
            print(f"       原文引用: {src[:120]}{'...' if len(src) > 120 else ''}", flush=True)
    print(f"       条款: {issue.get('explanation', '')}", flush=True)
    print(f"       建议: {issue.get('suggested_fix', '')}", flush=True)
    print(flush=True)


def test_upload_review_json(filepath: str):
    """上传文件并等待完整 JSON 审核结果"""
    print(f"\n{'='*60}")
    print(f"上传文件: {filepath}")
    print(f"模式: JSON（等待完整结果）")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/v1/review/upload-and-review"

    with open(filepath, "rb") as f:
        resp = requests.post(
            url,
            data={"response_format": "json"},
            files={"file": (filepath, f)},
            headers=HEADERS,
            timeout=300,
        )

    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"文件: {result.get('doc_id')}")
        print(f"状态: {result.get('status')}")
        issues = result.get("issues", [])
        summary = result.get("summary", {})
        print(f"问题总数: {summary.get('total', len(issues))}")
        print(f"  高风险: {summary.get('high', 0)}")
        print(f"  中风险: {summary.get('medium', 0)}")
        print(f"  低风险: {summary.get('low', 0)}")
        print()
        for i, issue in enumerate(issues, 1):
            _print_issue(issue, i)
    else:
        print(f"错误: {resp.text}")


def test_upload_review_stream(filepath: str):
    """上传文件并以 SSE 流式接收审核结果"""
    print(f"\n{'='*60}")
    print(f"上传文件: {filepath}")
    print(f"模式: SSE 流式")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/v1/review/upload-and-review"

    with open(filepath, "rb") as f:
        resp = requests.post(
            url,
            data={"response_format": "stream"},
            files={"file": (filepath, f)},
            headers=HEADERS,
            stream=True,
            timeout=300,
        )

    print(f"状态码: {resp.status_code}\n", flush=True)
    if resp.status_code != 200:
        print(f"错误: {resp.text}")
        return

    all_issues = []
    buf = ""
    batch_num = 0

    for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                continue
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
                if event_type == "complete":
                    print(f"\n--- 审核完成 ---", flush=True)
                    print(f"共收到 {len(all_issues)} 条问题", flush=True)
                elif event_type == "error":
                    print("\n--- 审核出错 ---", flush=True)
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str:
                    try:
                        issues = json.loads(data_str)
                        batch_num += 1
                        print(f"--- 第 {batch_num} 批（{len(issues)} 条）---", flush=True)
                        for issue in issues:
                            all_issues.append(issue)
                            _print_issue(issue, len(all_issues))
                    except json.JSONDecodeError:
                        print(f"  [raw] {data_str[:100]}", flush=True)


def test_upload_with_rules(filepath: str, rule_ids: list):
    """上传文件并指定规则 ID"""
    print(f"\n{'='*60}")
    print(f"上传文件: {filepath}")
    print(f"指定规则: {rule_ids}")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/v1/review/upload-and-review"

    with open(filepath, "rb") as f:
        resp = requests.post(
            url,
            data={"response_format": "json"},
            files={"file": (filepath, f)},
            params=[("rule_ids", rid) for rid in rule_ids],
            headers=HEADERS,
            timeout=300,
        )

    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        issues = result.get("issues", [])
        print(f"审核结果: {len(issues)} 条问题")
        for i, issue in enumerate(issues, 1):
            _print_issue(issue, i)
    else:
        print(f"错误: {resp.text}")


def test_health():
    """测试服务是否在线"""
    print("检测服务状态...")
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/rules", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            rules = resp.json()
            print(f"服务在线，当前有 {len(rules)} 条规则")
        else:
            print(f"服务响应异常: {resp.status_code}")
    except Exception as e:
        print(f"无法连接服务: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print(f"  python {sys.argv[0]} <pdf_or_image_path>          # JSON 模式审核")
        print(f"  python {sys.argv[0]} --stream <pdf_or_image_path>  # SSE 流式审核")
        print(f"  python {sys.argv[0]} --health                      # 检测服务状态")
        print()
        print("示例:")
        print(f"  python {sys.argv[0]} ticket.pdf")
        print(f"  python {sys.argv[0]} --stream ticket.pdf")
        print(f"  python {sys.argv[0]} --health")
        sys.exit(0)

    if sys.argv[1] == "--health":
        test_health()
    elif sys.argv[1] == "--stream":
        if len(sys.argv) < 3:
            print("请指定文件路径")
            sys.exit(1)
        test_health()
        test_upload_review_stream(sys.argv[2])
    else:
        test_health()
        test_upload_review_json(sys.argv[1])

#!/usr/bin/env python3
"""
RAG 训练 CLI 工具 - 通过 5100 端 /api/v1/sqlagent/training/add 训练数据
支持三种类型: ddl, documentation, sql
"""
import sys
import json
import argparse
import requests

API_BASE = "http://127.0.0.1:5100/api/v1/sqlagent"


def add_ddl(ddl_text: str):
    """添加 DDL 训练数据"""
    r = requests.post(f"{API_BASE}/training/add", json={"data_type": "ddl", "content": ddl_text})
    return r.json()


def add_documentation(doc_text: str):
    """添加文档训练数据"""
    r = requests.post(f"{API_BASE}/training/add", json={"data_type": "documentation", "content": doc_text})
    return r.json()


def add_sql(question: str, sql: str):
    """添加 SQL 训练数据"""
    r = requests.post(f"{API_BASE}/training/add", json={"data_type": "sql", "question": question, "sql": sql})
    return r.json()


def list_training(training_type: str = None):
    """列出已有训练数据"""
    params = {"training_type": training_type} if training_type else {}
    r = requests.get(f"{API_BASE}/training", params=params)
    return r.json()


def interactive_mode():
    """交互模式"""
    print("=" * 60)
    print("RAG 训练 CLI - 交互模式")
    print("=" * 60)
    print("命令:")
    print("  1) ddl <DDL 语句>")
    print("  2) doc <文档内容>")
    print("  3) sql <问题> :: <SQL>")
    print("  4) list [ddl|doc|sql]    # 列出已有")
    print("  5) import <file>          # 从 JSON 导入")
    print("  6) exit")
    print()

    while True:
        try:
            line = input("rag> ").strip()
        except EOFError:
            break
        if not line or line == "exit":
            break
        elif line.startswith("ddl "):
            result = add_ddl(line[4:].strip())
            print(f"  → {result}")
        elif line.startswith("doc "):
            result = add_documentation(line[4:].strip())
            print(f"  → {result}")
        elif line.startswith("sql "):
            parts = line[4:].split("::", 1)
            if len(parts) != 2:
                print("  格式: sql <问题> :: <SQL>")
                continue
            result = add_sql(parts[0].strip(), parts[1].strip())
            print(f"  → {result}")
        elif line.startswith("list"):
            t = line.split(" ", 1)[1] if " " in line else None
            result = list_training(t)
            if isinstance(result, dict):
                items = result.get("data", [])
                print(f"  共 {len(items)} 条")
                for it in items[:20]:
                    t = it.get("training_data_type", "?")
                    content = it.get("content") or it.get("sql") or ""
                    print(f"    [{t}] {content[:80]!r}")
        elif line.startswith("import "):
            filepath = line[7:].strip()
            try:
                with open(filepath) as f:
                    data = json.load(f)
                count = 0
                for item in data:
                    t = item.get("type")
                    if t == "ddl":
                        add_ddl(item["content"])
                    elif t in ("doc", "documentation"):
                        add_documentation(item["content"])
                    elif t == "sql":
                        add_sql(item["question"], item["sql"])
                    count += 1
                print(f"  ✓ 导入 {count} 条")
            except Exception as e:
                print(f"  ✗ 导入失败: {e}")
        else:
            print("  未知命令")


def main():
    parser = argparse.ArgumentParser(description="RAG 训练 CLI - 调用 5100 端 API")
    parser.add_argument("--type", choices=["ddl", "doc", "sql"], help="训练数据类型")
    parser.add_argument("--content", help="DDL 或文档内容")
    parser.add_argument("--question", help="SQL 类型: 问题")
    parser.add_argument("--sql", help="SQL 类型: SQL 语句")
    parser.add_argument("--file", help="从 JSON 文件批量导入 (格式: [{type, content/question, sql}])")
    parser.add_argument("--list", action="store_true", help="列出已有训练数据")
    parser.add_argument("--list-type", choices=["ddl", "doc", "sql"], help="列出指定类型")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.list:
        result = list_training(args.list_type)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.file:
        try:
            with open(args.file) as f:
                data = json.load(f)
            for item in data:
                t = item.get("type")
                if t == "ddl":
                    print(add_ddl(item["content"]))
                elif t in ("doc", "documentation"):
                    print(add_documentation(item["content"]))
                elif t == "sql":
                    print(add_sql(item["question"], item["sql"]))
        except Exception as e:
            print(f"导入失败: {e}")
    elif args.type == "ddl" and args.content:
        print(add_ddl(args.content))
    elif args.type in ("doc", "documentation") and args.content:
        print(add_documentation(args.content))
    elif args.type == "sql" and args.question and args.sql:
        print(add_sql(args.question, args.sql))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

"""
Hermes subprocess 服务 - 调 hermes -z 审查作业票

架构:
  不用 Popen 单例 (hermes --tui 需要 TTY, 不能 stdin 通信)
  改用 subprocess.run + 预热策略

实测数据:
  第一次启动 hermes: ~12s
  hermes LLM 推理 (qwen3.6:35b): ~5-15s
  总审查时间: ~17-27s

优化: 第一次审查时启动 hermes, 后续用 --continue 续接 (省部分 LLM 初始化)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HERMES_BIN = "/home/czys/.local/bin/hermes"
HERMES_SESSION_DIR = Path("/tmp/hermes_sessions")
HERMES_SESSION_DIR.mkdir(parents=True, exist_ok=True)

# 单 session 模式: 第一次启动 → 后续 --continue
# (subprocess.run 每次新进程, 但 LLM 模型加载可省 1-2s)
_LAST_SESSION_ID: Optional[str] = None
_LOCK = asyncio.Lock()


async def call_hermes(prompt: str, timeout: int = 120) -> str:
    """
    调 hermes 处理 prompt, 返 stdout
    
    重要: hermes -z 是单次模式, 每次新进程都是独立上下文, 不保存记忆.
    ⚠️ 不用 --resume, 因为:
      1. 不同用户/不同任务的 prompt 不应该共享上下文
      2. 作业票审查 和 智能问数 是不同的场景, 记忆会污染
      3. 之前留的 _LAST_SESSION_ID 是 bug, 已移除
    """
    
    # 永远新 session (不用 --resume)
    # ⚠️ 2026-06-29: 云端 glm-5.2 5h 额度耗尽 (HTTP 429), 改用本地 ollama qwen3.6:35b
    # ⚠️ 2026-06-30: 移除 --skills llm-wiki, 法规原文已由 gb30871.py 直接注入 prompt
    #    不加载 skill → hermes 只做纯 LLM 推理, 不再内部调 wiki → 大幅减少耗时
    cmd = [HERMES_BIN, "-z", prompt, "--yolo", "-m", "qwen3.6:35b", "--provider", "ollama"]  # --yolo 自动批准 hooks
    
    env = os.environ.copy()
    env["HERMES_ACCEPT_HOOKS"] = "1"  # headless 自动批准
    
    t0 = time.time()
    
    def _run():
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    
    try:
        proc = await asyncio.get_event_loop().run_in_executor(None, _run)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"hermes 处理超时 ({timeout}s)")
    except FileNotFoundError:
        raise RuntimeError(f"hermes 命令未找到: {HERMES_BIN}")
    
    elapsed = time.time() - t0
    logger.info("hermes 调完成 (%.1fs, stdout=%d 字符)", elapsed, len(proc.stdout))
    
    if proc.returncode != 0:
        logger.warning("hermes returncode=%d, stderr=%s", proc.returncode, proc.stderr[:500])
    
    return proc.stdout


def _extract_session_id(output: str) -> Optional[str]:
    """hermes 输出可能含 session id (现在不用了, 保留以备未来)"""
    m = re.search(r"session[_\s-]?id[:\s]+([a-zA-Z0-9_-]+)", output, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def extract_json(text: str) -> Optional[dict]:
    """从 hermes markdown 输出中提取 JSON (3 层 fallback)"""
    
    # 1) 抓 ```json 代码块
    m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            return {"results": json.loads(m.group(1).strip()), "method": "json_code_block"}
        except Exception:
            pass
    
    # 2) 抓 ``` 代码块
    m = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        try:
            return {"results": json.loads(m.group(1).strip()), "method": "code_block"}
        except Exception:
            pass
    
    # 3) 找 [{...}] 数组
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if m:
        try:
            return {"results": json.loads(m.group(0)), "method": "regex_array"}
        except Exception:
            pass
    
    return None


def call_hermes_sync(prompt: str, timeout: int = 120):
    """
    同步版 call_hermes - 给 streaming.py (sync generator) 用

    实现: 直接 subprocess.run 同步阻塞读 stdout, 不绕 asyncio。
    之前用 asyncio.run_coroutine_threadsafe + new_event_loop 在 sync generator 上下文里
    拿不到完整 stdout (streaming.py 里 wiki_enhancement 是空), 改成直接 subprocess.run。

    Args:
        prompt: 给 hermes 的 prompt
        timeout: 超时秒数

    Yields:
        {"type": "step", "action": "...", "status": "running"}  ← 中间进度事件
        "stdout 内容"  ← hermes 最终输出字符串 (最后一项)

    Raises:
        RuntimeError: hermes 失败 / 超时
    """
    env = os.environ.copy()
    env["HERMES_ACCEPT_HOOKS"] = "1"
    # 关键: 必须传 --skills llm-wiki, hermes 才会加载 llm-wiki skill 并激活 wiki 检索工具
    # 之前漏了, hermes -z 默认不加载 skill, 只能靠 LLM 训练数据硬答 (查 wiki 库等于失效)
    cmd = [HERMES_BIN, "-z", prompt, "--skills", "llm-wiki", "--yolo"]

    t0 = time.time()
    stdout_buf = []

    # 用 Popen 流式读 stdout, 每读一行 yield 一次进度事件
    # 让前端在 hermes 跑长任务时能看到 "在查 wiki / 在合成报告" 等中间状态
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,  # 行缓冲
        )
    except FileNotFoundError:
        raise RuntimeError(f"hermes 命令未找到: {HERMES_BIN}")

    # 阶段 1: 启动提示
    yield {"type": "step", "action": "🚀 启动智能引擎...", "tool_name": "engine_progress", "status": "running"}

    # 阶段 2: 轮询读取 stdout, 每行 yield 进度
    last_yield_time = time.time()
    line_count = 0
    import select as _select
    stdout_pipe = proc.stdout  # 类型收窄 (pyright 嫌 None 不安全)
    assert stdout_pipe is not None
    while True:
        # 超时检查
        elapsed = time.time() - t0
        if elapsed > timeout:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"处理超时 ({timeout}s)")

        # 非阻塞读 stdout (避免 CPU 100%)
        ready, _, _ = _select.select([stdout_pipe], [], [], 0.5)
        if ready:
            line = stdout_pipe.readline()
            if not line:
                # EOF: 进程结束
                break
            stdout_buf.append(line)
            line_count += 1
            # 每 5s yield 一次进度 (避免 SSE 洪水)
            if time.time() - last_yield_time > 5:
                last_yield_time = time.time()
                yield {
                    "type": "step",
                    "action": f"🔄 知识库检索中 (已读 {line_count} 段, 累计 {elapsed:.0f}s)",
                    "tool_name": "engine_progress",
                    "status": "running",
                    "update": True,
                }

        # 检查进程是否结束
        if proc.poll() is not None:
            # 读完剩余 stdout
            remaining = stdout_pipe.read()
            if remaining:
                stdout_buf.append(remaining)
            break

    elapsed = time.time() - t0
    full_stdout = "".join(stdout_buf)
    logger.info(
        "hermes_sync 调完成 (%.1fs, stdout=%d 字符, %d 行, returncode=%d)",
        elapsed, len(full_stdout), line_count, proc.returncode,
    )

    if proc.returncode != 0 and proc.stderr:
        logger.warning("hermes returncode=%d, stderr=%s", proc.returncode, (proc.stderr.read() or "")[:500])

    yield full_stdout or ""


async def is_hermes_available() -> bool:
    """检查 hermes 命令是否可用 (不实际调 hermes, 只检查二进制文件存在)"""
    import os
    return os.path.isfile(HERMES_BIN) and os.access(HERMES_BIN, os.X_OK)

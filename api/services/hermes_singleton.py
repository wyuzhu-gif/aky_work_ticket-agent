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
    """
    global _LAST_SESSION_ID
    
    cmd = [HERMES_BIN, "-z", prompt, "--yolo"]  # --yolo 自动批准 hooks
    
    # 续接 session (省 LLM 初始化)
    if _LAST_SESSION_ID:
        cmd.extend(["--resume", _LAST_SESSION_ID])
    
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
    
    # 尝试提取 session id (hermes --resume 需要)
    session_id = _extract_session_id(proc.stdout) or _extract_session_id(proc.stderr)
    if session_id:
        _LAST_SESSION_ID = session_id
        logger.debug("捕获 hermes session: %s", session_id)
    
    return proc.stdout


def _extract_session_id(output: str) -> Optional[str]:
    """hermes 输出可能含 session id, 提取出来续接用"""
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


def call_hermes_sync(prompt: str, timeout: int = 120) -> str:
    """
    同步版 call_hermes - 给 streaming.py (sync generator) 用
    
    用 asyncio.run 包一层, 因为 streaming.py 是 def (不是 async def),
    不能直接 await. 这个函数牺牲并发性换简单性.
    
    Args:
        prompt: 给 hermes 的 prompt
        timeout: 超时秒数
    
    Returns:
        hermes 输出文本
    
    Raises:
        RuntimeError: hermes 失败 / 超时
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(call_hermes(prompt, timeout=timeout))
        finally:
            loop.close()
    except Exception as e:
        raise RuntimeError(f"call_hermes_sync failed: {e}") from e


async def is_hermes_available() -> bool:
    """检查 hermes 命令是否可用"""
    try:
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run([HERMES_BIN, "--version"], capture_output=True, timeout=5)
        )
        return proc.returncode == 0
    except Exception:
        return False

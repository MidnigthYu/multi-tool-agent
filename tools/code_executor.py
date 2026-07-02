from __future__ import annotations

import ast
import asyncio
import contextlib
import logging
import os as _os
import tempfile
import time as _time

from pydantic import BaseModel, Field

from config.settings import get_settings

logger = logging.getLogger(__name__)


_DANGEROUS_MODULES: set[str] = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "ctypes",
    "signal",
    "multiprocessing",
    "threading",
    "requests",
    "urllib",
    "http",
    "pathlib",
    "tempfile",
    "pickle",
    "shelve",
    "builtins",
    "platform",
    "pwd",
    "grp",
    "resource",
    "fcntl",
    "mmap",
    "ptty",
    "tty",
}

_DANGEROUS_BUILTINS: set[str] = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "breakpoint",
    "input",
}

_DANGEROUS_ATTR_CALLS: set[str] = {
    "system",
    "popen",
    "call",
    "run",
    "check_output",
    "Popen",
    "connect",
    "send",
    "recv",
    "bind",
    "listen",
    "remove",
    "unlink",
    "rmdir",
    "makedirs",
    "chmod",
    "chown",
}

_SAFE_DUNDER_METHODS: set[str] = {
    "__init__",
    "__str__",
    "__repr__",
    "__len__",
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__contains__",
    "__iter__",
    "__next__",
    "__enter__",
    "__exit__",
    "__call__",
    "__add__",
    "__sub__",
    "__mul__",
    "__truediv__",
    "__floordiv__",
    "__mod__",
    "__pow__",
    "__and__",
    "__or__",
    "__xor__",
    "__lshift__",
    "__rshift__",
    "__neg__",
    "__pos__",
    "__abs__",
    "__invert__",
    "__eq__",
    "__ne__",
    "__lt__",
    "__le__",
    "__gt__",
    "__ge__",
    "__hash__",
    "__bool__",
    "__int__",
    "__float__",
    "__complex__",
    "__index__",
    "__new__",
    "__del__",
    "__aenter__",
    "__aexit__",
    "__aiter__",
    "__anext__",
    "__await__",
}


def _validate_code_safety(code: str) -> tuple[bool, str]:
    """AST-based static analysis for code safety.

    Uses ast.parse + ast.walk to detect dangerous patterns in user-submitted
    Python code with zero regex dependency, avoiding string-content false positives.

    Returns:
        (True, "") if code is safe or has syntax errors (pass-through).
        (False, reason) if dangerous patterns are detected.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True, ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _DANGEROUS_MODULES:
                    return False, f"危险导入被拦截: {alias.name}"
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in _DANGEROUS_MODULES:
                return False, f"危险导入被拦截: {node.module}"

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_BUILTINS:
            return False, f"危险函数调用被拦截: {node.func.id}()"

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DANGEROUS_ATTR_CALLS
        ):
            return False, (f"危险方法调用被拦截: .{node.func.attr}()")

        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in _SAFE_DUNDER_METHODS:
            return False, f"私有属性访问被拦截: .{node.attr}"

    return True, ""


class CodeExecutionInput(BaseModel):
    """代码执行工具入参 Schema，适配 ToolRegistry 注册规范。

    提供 AST 静态安全校验后的 Python 代码执行能力，
    支持自定义超时时间，适用于沙箱容器内执行场景。
    """

    code: str = Field(..., min_length=1, max_length=5000, description="待执行 Python 代码")
    timeout: int | None = Field(default=None, ge=1, le=30, description="自定义容器超时，范围1~30s")


async def _execute_in_container(code: str, timeout: int) -> tuple[int, str, float]:
    """Execute Python code inside a Docker sandbox container.

    Writes code to a temporary file, invokes docker run with strict isolation
    flags, and captures the combined stdout/stderr output.

    Returns:
        (exit_code, output, elapsed_seconds)
    """
    t_start = _time.monotonic()
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp_path = f.name
        container_tag = "multi-tool-agent-sandbox:latest"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--memory=256m",
            "--cpus=0.5",
            "-v",
            f"{tmp_path}:/tmp/user_code.py:ro",
            "-e",
            "SANDBOX_CODE_FILE=/tmp/user_code.py",
            container_tag,
        ]
        effective = timeout + 5
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=effective)
            exit_code = proc.returncode or 0
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
        except TimeoutError:
            proc.kill()
            exit_code = 124
            output = "[SANDBOX_TIMEOUT]"
        elapsed = _time.monotonic() - t_start
        return exit_code, output, elapsed
    except FileNotFoundError:
        logger.error("[code_executor] Docker binary not found")
        return -1, "[SANDBOX_DEGRADED] Docker 不可用，请检查环境配置", _time.monotonic() - t_start
    except Exception as e:
        logger.error("[code_executor] Container dispatch failed: %s", e)
        return -2, f"[SANDBOX_ERROR] 容器调度异常: {e}", _time.monotonic() - t_start
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            with contextlib.suppress(Exception):
                _os.unlink(tmp_path)


async def code_executor(code: str, timeout: int | None = None) -> str:
    """ToolRegistry-compatible code execution entry point.

    Three-layer pipeline:
        1. AST static safety check (_validate_code_safety)
        2. Docker container dispatch (_execute_in_container)
        3. Output formatting and truncation

    All execution paths return a string. No exception propagates upward
    to the LangGraph layer, ensuring agent workflow continuity.
    """
    safe, reason = _validate_code_safety(code)
    if not safe:
        logger.warning("[code_executor] Blocked by AST check: %s", reason)
        return f"[CODE_BLOCKED] {reason}"
    effective_timeout = timeout if timeout is not None else get_settings().CODE_SANDBOX_SOFT_TIMEOUT_S
    try:
        exit_code, raw_output, elapsed = await _execute_in_container(code, effective_timeout)
    except Exception as e:
        logger.error("[code_executor] _execute_in_container raised: %s", e)
        return f"[CODE_DEGRADED] 代码执行异常: {e}"
    if exit_code == 124:
        logger.warning("[code_executor] Timeout after %.1fs", elapsed)
        return f"[CODE_TIMEOUT] 代码执行超时（{effective_timeout}s），请优化算法或减少计算量"
    if exit_code == -1:
        logger.error("[code_executor] Docker unavailable")
        return "[CODE_DEGRADED] 沙箱容器暂不可用，请稍后重试"
    if exit_code == -2:
        logger.error("[code_executor] Dispatch degraded: %s", raw_output)
        return f"[CODE_DEGRADED] {raw_output}"
    if exit_code != 0:
        logger.warning("[code_executor] Crash exit=%d", exit_code)
        return f"[CODE_CRASH] 代码执行崩溃（exit code {exit_code}），请检查代码逻辑\n{raw_output.strip()}"
    output = raw_output.strip()
    max_chars = get_settings().CODE_SANDBOX_MAX_OUTPUT_CHARS
    if len(output) > max_chars:
        output = output[:max_chars] + "\n[OUTPUT_TRUNCATED]"
    logger.info("[code_executor] Success in %.1fs", elapsed)
    return output

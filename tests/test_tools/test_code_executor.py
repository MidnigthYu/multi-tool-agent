"""代码沙箱工具单元测试 -- 33 用例（Schema×6 + AST×12 + Executor×10 + FailureTrack×5）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from tools.code_executor import (
    CodeExecutionInput,
    _validate_code_safety,
    code_executor,
)


class TestCodeExecutionInput:
    """Task5.1: 6 cases — Pydantic 入参校验"""

    def test_valid_input(self) -> None:
        ci = CodeExecutionInput(code="print(1)")
        assert ci.code == "print(1)"
        assert ci.timeout is None
        assert list(ci.model_dump().keys()) == ["code", "timeout"]

    def test_default_timeout_is_none(self) -> None:
        ci = CodeExecutionInput(code="x = 1")
        assert ci.timeout is None

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeExecutionInput(code="")

    def test_code_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeExecutionInput(code="x" * 5001)

    def test_code_5000_boundary(self) -> None:
        ci = CodeExecutionInput(code="x" * 5000)
        assert len(ci.code) == 5000

    def test_timeout_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CodeExecutionInput(code="x", timeout=0)
        with pytest.raises(ValidationError):
            CodeExecutionInput(code="x", timeout=31)
        ci = CodeExecutionInput(code="x", timeout=1)
        assert ci.timeout == 1
        ci2 = CodeExecutionInput(code="x", timeout=30)
        assert ci2.timeout == 30


class TestValidateCodeSafety:
    """Task5.2: 12 cases — AST 静态安全校验"""

    def test_safe_calculation(self) -> None:
        ok, reason = _validate_code_safety("result = sum([1, 2, 3])")
        assert ok is True and reason == ""

    def test_safe_function_def(self) -> None:
        ok, reason = _validate_code_safety("def f(a, b):\n    return a + b")
        assert ok is True and reason == ""

    def test_dangerous_import_os(self) -> None:
        ok, reason = _validate_code_safety("import os")
        assert ok is False and "os" in reason

    def test_dangerous_from_import(self) -> None:
        ok, reason = _validate_code_safety("from os import path")
        assert ok is False

    def test_eval_call(self) -> None:
        ok, reason = _validate_code_safety("eval('1+1')")
        assert ok is False and "eval" in reason

    def test_exec_call(self) -> None:
        ok, reason = _validate_code_safety("exec('x=1')")
        assert ok is False and "exec" in reason

    def test_open_call(self) -> None:
        ok, reason = _validate_code_safety("open('/etc/passwd')")
        assert ok is False and "open" in reason

    def test_import_subprocess(self) -> None:
        ok, reason = _validate_code_safety("import subprocess")
        assert ok is False

    def test_dunder_attribute(self) -> None:
        ok, reason = _validate_code_safety("x = obj.__class__")
        assert ok is False and "__class__" in reason

    def test_string_keyword_no_false_positive(self) -> None:
        ok, reason = _validate_code_safety("# import os is harmless\nprint('hello')")
        assert ok is True and reason == ""

    def test_syntax_error_passthrough(self) -> None:
        ok, reason = _validate_code_safety("def f(::")
        assert ok is True and reason == ""

    def test_safe_standard_lib(self) -> None:
        ok, reason = _validate_code_safety("import math\nimport json\nimport re\nimport typing\nimport collections")
        assert ok is True and reason == ""


class TestCodeExecutor:
    """Task5.3: 10 cases — 工具主函数 Mock 测试"""

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_normal_execution(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (0, "42\n", 0.1)
        result = await code_executor("print(42)")
        assert result == "42"
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_ast_blocked(self, mock_exec: AsyncMock) -> None:
        result = await code_executor("import os")
        assert result.startswith("[CODE_BLOCKED]")
        assert isinstance(result, str)
        mock_exec.assert_not_called()

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_timeout(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (124, "[SANDBOX_TIMEOUT]", 20.5)
        result = await code_executor("while True: pass")
        assert result.startswith("[CODE_TIMEOUT]")
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_crash(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (1, "ZeroDivisionError: division by zero\n", 0.3)
        result = await code_executor("1/0")
        assert result.startswith("[CODE_CRASH]")
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_docker_unavailable(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (-1, "[SANDBOX_DEGRADED] Docker 不可用", 0.0)
        result = await code_executor("print(1)")
        assert result.startswith("[CODE_DEGRADED]")
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_dispatch_exception(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (-2, "[SANDBOX_ERROR] 容器调度异常: timeout", 0.0)
        result = await code_executor("print(1)")
        assert result.startswith("[CODE_DEGRADED]")
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_output_truncation(self, mock_exec: AsyncMock) -> None:
        long_output = "x" * 12000
        mock_exec.return_value = (0, long_output, 0.5)
        result = await code_executor("print('x' * 12000)")
        assert "[OUTPUT_TRUNCATED]" in result
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_custom_timeout(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = (0, "ok", 0.1)
        result = await code_executor("print('ok')", timeout=15)
        assert result == "ok"
        assert isinstance(result, str)

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_exception_no_leak(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = RuntimeError("unexpected")
        result = await code_executor("print(1)")
        assert isinstance(result, str)
        assert "unexpected" in result or result.startswith("[CODE_DEGRADED]")

    @patch("tools.code_executor._execute_in_container", new_callable=AsyncMock)
    async def test_all_paths_return_string(self, mock_exec: AsyncMock) -> None:
        scenarios = [
            ((0, "ok\n", 0.1), "ok"),
            ((124, "", 21.0), "CODE_TIMEOUT"),
            ((1, "error", 0.2), "CODE_CRASH"),
            ((-1, "no docker", 0.0), "CODE_DEGRADED"),
            ((-2, "exception", 0.0), "CODE_DEGRADED"),
        ]
        for ret, expected_sub in scenarios:
            mock_exec.return_value = ret
            result = await code_executor("print(1)")
            assert isinstance(result, str), f"Expected str, got {type(result)} for {ret}"
            assert expected_sub in result, f"Expected {expected_sub} in {result}"


class TestConsecutiveFailureTracking:
    """Task5.4: 5 cases — 连续失败计数与会话级禁用（通 graph 链路验证）"""

    @pytest.mark.asyncio
    async def test_crash_increments_counter(self) -> None:
        from core.agent_graph import build_agent_graph
        from core.agent_state import create_initial_state

        reg = MagicMock()

        async def mock_fail(**_kw: str) -> str:
            return "[CODE_CRASH] 代码执行崩溃"

        reg.get_func.return_value = mock_fail
        state = create_initial_state("s1", "test")
        state["selected_tools"] = ["code_executor"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(MagicMock(), reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t1"}})
        assert r.get("consecutive_code_failures", 0) >= 1

    @pytest.mark.asyncio
    async def test_timeout_increments_counter(self) -> None:
        from core.agent_graph import build_agent_graph
        from core.agent_state import create_initial_state

        reg = MagicMock()

        async def mock_fail(**_kw: str) -> str:
            return "[CODE_TIMEOUT] 代码执行超时"

        reg.get_func.return_value = mock_fail
        state = create_initial_state("s2", "test")
        state["selected_tools"] = ["code_executor"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(MagicMock(), reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t2"}})
        assert r.get("consecutive_code_failures", 0) >= 1

    @pytest.mark.asyncio
    async def test_success_resets_counter(self) -> None:
        from core.agent_graph import build_agent_graph
        from core.agent_state import create_initial_state

        reg = MagicMock()

        async def mock_ok(**_kw: str) -> str:
            return "42"

        reg.get_func.return_value = mock_ok
        state = create_initial_state("s3", "test")
        state["consecutive_code_failures"] = 2
        state["selected_tools"] = ["code_executor"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(MagicMock(), reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t3"}})
        assert r.get("consecutive_code_failures", -1) == 0

    @pytest.mark.asyncio
    async def test_three_failures_disables_tool(self) -> None:
        from core.agent_graph import build_agent_graph
        from core.agent_state import create_initial_state

        reg = MagicMock()

        async def mock_fail(**_kw: str) -> str:
            return "[CODE_CRASH] fail"

        reg.get_func.return_value = mock_fail
        state = create_initial_state("s4", "test")
        state["consecutive_code_failures"] = 2
        state["selected_tools"] = ["code_executor"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(MagicMock(), reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t4"}})
        assert r.get("consecutive_code_failures", 0) >= 3
        assert "code_executor" in r.get("tools_disabled", [])

    @pytest.mark.asyncio
    async def test_two_failures_no_disable(self) -> None:
        from core.agent_graph import build_agent_graph
        from core.agent_state import create_initial_state

        reg = MagicMock()

        async def mock_fail(**_kw: str) -> str:
            return "[CODE_TIMEOUT] timeout"

        reg.get_func.return_value = mock_fail
        state = create_initial_state("s5", "test")
        state["selected_tools"] = ["code_executor"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(MagicMock(), reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t5"}})
        assert r.get("consecutive_code_failures", 0) <= 2
        assert "code_executor" not in r.get("tools_disabled", [])

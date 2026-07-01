"""pytest 共享 fixtures — 全局单例重置 + 环境变量隔离 + 路由Mock。"""

from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Generator
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from storage.sqlite_client import SQLiteClient

_SINGLETON_RESETS: list[tuple[str, str]] = [
    ("config.settings", "_settings"),
    ("config.env_validator", "_TEST_MODE"),
    ("core.logger", "_LOGGING_SETUP_DONE"),
    ("core.model_adapter", "_adapter_instance"),
    ("core.tool_registry", "_registry_instance"),
    ("storage.chroma_client", "_chroma_instance"),
    ("storage.sqlite_client", "_sqlite_instance"),
    ("storage.file_store", "_instance"),
    ("memory.short_term", "_short_term_instance"),
    ("memory.mid_term", "_mid_instance"),
    ("memory.long_term", "_long_term_instance"),
]


def _reset_all_singletons() -> None:
    for mod_name, attr in _SINGLETON_RESETS:
        try:
            mod = importlib.import_module(mod_name)
            if attr == "_TEST_MODE":
                mod.set_test_mode(False)
            else:
                setattr(mod, attr, None)
        except (ImportError, AttributeError):
            pass


@pytest.fixture(autouse=True)
def _env_setup() -> Generator[None, None, None]:
    _reset_all_singletons()
    old: dict[str, str | None] = {}
    for k in [
        "LLM_DEEPSEEK_API_KEY",
        "LLM_DEEPSEEK_BASE_URL",
        "LLM_DEEPSEEK_MODEL",
        "LLM_DOUBAO_API_KEY",
        "LLM_DOUBAO_BASE_URL",
        "LLM_DOUBAO_MODEL",
    ]:
        old[k] = os.environ.get(k)
        os.environ[k] = "test-" + k.lower()
    old["TAVILY_API_KEY"] = os.environ.get("TAVILY_API_KEY")
    os.environ["TAVILY_API_KEY"] = "mock-tavily-key-001"
    for k in ["CHROMA_PERSIST_DIR", "SQLITE_DB_PATH", "UPLOAD_DIR"]:
        old.setdefault(k, os.environ.get(k))
        tmpdir = tempfile.mkdtemp()
        suffix = "/chroma" if k == "CHROMA_PERSIST_DIR" else "/sessions.db" if k == "SQLITE_DB_PATH" else "/uploads"
        os.environ[k] = tmpdir + suffix
    import config.settings as _cs

    _cs._settings = None
    import config.env_validator as _ev

    _ev.set_test_mode(True)
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset_all_singletons()


@pytest.fixture
def sample_messages() -> list:
    return [HumanMessage(content="你好"), AIMessage(content="你好！"), HumanMessage(content="天气？")]


@pytest.fixture
def mock_ai_message() -> AIMessage:
    msg = AIMessage(content="测试回复")
    msg.response_metadata = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    return msg


@pytest.fixture
def mock_model_adapter(mock_ai_message: AIMessage) -> Generator[MagicMock, None, None]:
    adapter = MagicMock()

    async def invoke(state: Any, _messages: Any = None, **_kwargs: Any) -> tuple[Any, Any]:
        return mock_ai_message, dict(state)

    adapter.invoke = invoke
    with patch("core.router_node.get_model_adapter", return_value=adapter):
        yield adapter


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    reg = MagicMock()
    reg.list_tools.return_value = [{"name": "test_tool", "description": "Test tool", "parameters": {}}]
    reg.get_func.return_value = AsyncMock(return_value="tool_result")
    return reg


@pytest.fixture
def temp_sqlite() -> Generator[SQLiteClient, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    client = SQLiteClient(path)
    yield client
    client.close()
    with suppress(PermissionError):
        os.unlink(path)


def sample_agent_state(**overrides: Any) -> dict[str, Any]:
    from core.agent_state import create_initial_state

    s = create_initial_state("test-session-001", "测试消息")
    s.update(overrides)
    return s

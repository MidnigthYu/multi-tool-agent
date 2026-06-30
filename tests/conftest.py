"""pytest 共享 fixtures。"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture(autouse=True)
def _env_setup() -> Generator[None, None, None]:
    old = {}
    for k in [
        "LLM_DEEPSEEK_API_KEY",
        "LLM_DEEPSEEK_BASE_URL",
        "LLM_DEEPSEEK_MODEL",
        "LLM_DOUBAO_API_KEY",
        "LLM_DOUBAO_BASE_URL",
        "LLM_DOUBAO_MODEL",
        "TAVILY_API_KEY",
    ]:
        old[k] = os.environ.get(k)
        os.environ[k] = "test-" + k.lower()
    os.environ["CHROMA_PERSIST_DIR"] = "/tmp/test_chroma"
    os.environ["SQLITE_DB_PATH"] = "/tmp/test_sessions.db"
    os.environ["UPLOAD_DIR"] = "/tmp/test_uploads"
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for k in ["CHROMA_PERSIST_DIR", "SQLITE_DB_PATH", "UPLOAD_DIR"]:
        os.environ.pop(k, None)


@pytest.fixture
def sample_messages() -> list:
    return [HumanMessage(content="你好"), AIMessage(content="你好！"), HumanMessage(content="天气？")]


@pytest.fixture
def mock_ai_message() -> AIMessage:
    msg = AIMessage(content="测试回复")
    msg.response_metadata = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    return msg


@pytest.fixture
def mock_model_adapter(mock_ai_message: AIMessage) -> MagicMock:
    adapter = MagicMock()

    async def invoke(state: Any, _messages: Any = None, **_kwargs: Any) -> tuple[Any, Any]:
        return mock_ai_message, dict(state)

    adapter.invoke = invoke
    return adapter


@pytest.fixture
def mock_tool_registry() -> MagicMock:
    registry = MagicMock()
    registry.list_tools.return_value = [{"name": "test_tool", "description": "Test tool", "parameters": {}}]
    registry.get_func.return_value = AsyncMock(return_value="tool_result")
    return registry


def sample_agent_state(**overrides: Any) -> dict[str, Any]:
    from core.agent_state import create_initial_state

    state = create_initial_state("test-session-001", "测试消息")
    state.update(overrides)
    return state

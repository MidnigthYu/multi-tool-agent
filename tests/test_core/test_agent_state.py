"""AgentState 字段完整性测试。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from core.agent_state import AgentState, create_initial_state, merge_agent_state


class TestAgentState:
    def test_create_initial_state(self) -> None:
        state = create_initial_state("s1", "你好")
        assert state["session_id"] == "s1"
        assert len(state["messages"]) == 1
        assert isinstance(state["messages"][0], HumanMessage)
        assert state["messages"][0].content == "你好"
        assert state["fallback_flag"] is False
        assert state["model_retry_count"] == 0
        assert state["chroma_degraded"] is False
        assert state["tools_disabled"] == []
        assert state["memory_context"] == {}
        assert state["tool_calls"] == []
        assert state["tool_results"] == {}
        assert "model_name" in state and "observability" in state

    def test_observability_token_usage(self) -> None:
        tu = create_initial_state("s2", "test")["observability"]["token_usage"]
        assert tu["prompt_tokens"] >= 0 and tu["total_tokens"] >= 0

    def test_merge_messages(self) -> None:
        s1 = create_initial_state("s1", "msg1")
        s2: AgentState = {
            "messages": [AIMessage(content="reply1")],
            "session_id": "s1",
            "model_name": "m",
            "model_retry_count": 0,
            "fallback_flag": False,
            "chroma_degraded": False,
            "tools_disabled": [],
            "memory_context": {},
            "tool_calls": [],
            "tool_results": {},
            "observability": {
                "node_timings": {},
                "errors": [],
                "warnings": [],
                "degraded_flags": {},
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        }
        merged = merge_agent_state(s1, s2)
        assert len(merged["messages"]) == 2

    def test_tool_results_type(self) -> None:
        state = create_initial_state("s3", "hi")
        state["tool_results"]["search"] = "result text"
        assert isinstance(state["tool_results"], dict)
        assert state["tool_results"]["search"] == "result text"

    def test_required_fields_all_present(self) -> None:
        state = create_initial_state("s4", "")
        for f in [
            "messages",
            "session_id",
            "model_name",
            "model_retry_count",
            "fallback_flag",
            "chroma_degraded",
            "tools_disabled",
            "memory_context",
            "tool_calls",
            "tool_results",
            "observability",
        ]:
            assert f in state

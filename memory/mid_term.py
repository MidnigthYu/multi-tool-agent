"""L2 中期摘要缓存 -- SQLite 会话快照 + 自动摘要触发。"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import HumanMessage, SystemMessage

from config.constants import Constants
from config.settings import get_settings
from storage.sqlite_client import SQLiteClient

if TYPE_CHECKING:
    from core.model_adapter import ModelAdapter
logger = logging.getLogger(__name__)


class MidTermMemory:
    def __init__(self, sqlite_client: SQLiteClient, model_adapter: ModelAdapter | None = None) -> None:
        self._sqlite = sqlite_client
        self._model_adapter = model_adapter

    def add_turn(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        self._sqlite.save_message(session_id, "user", user_msg)
        self._sqlite.save_message(session_id, "assistant", assistant_msg)
        session = self._sqlite.get_session(session_id)
        if session is None or (session.get("summary", "") or ""):
            return
        msgs = self._sqlite.get_messages(session_id)
        rounds = len([m for m in msgs if m["role"] == "user"])
        if rounds >= get_settings().SESSION_MAX_ROUNDS:
            self._generate_summary(session_id, msgs)

    def _generate_summary(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        if self._model_adapter is None:
            logger.warning("ModelAdapter not available")
            return
        dialogue = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in messages[-40:])
        prompt = SystemMessage(content=Constants.SUMMARY_PROMPT_TEMPLATE)
        user = HumanMessage(content=f"请为以下对话生成摘要：\n\n{dialogue}")
        from core.agent_state import create_initial_state

        dummy = create_initial_state(session_id, "")
        try:
            import asyncio

            result, _ = asyncio.run(self._model_adapter.invoke(dummy, [prompt, user], temperature=0.3))
            raw = result.content
            if not isinstance(raw, str):
                raw = str(raw)
            content = raw.strip()
            try:
                parsed = json.loads(content)
                summary_text = json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
                logger.warning("Summary JSON parse failed")
                summary_text = json.dumps(
                    {"intent": content[:200], "conclusion": "无", "todos": [], "preferences": []}, ensure_ascii=False
                )
            self._sqlite.update_summary(session_id, summary_text)
        except Exception as e:
            logger.warning("Summary generation failed: %s", e)

    def get_summary(self, session_id: str) -> dict[str, Any] | None:
        session = self._sqlite.get_session(session_id)
        if session is None or not session.get("summary", ""):
            return None
        try:
            return cast(dict[str, Any], json.loads(session["summary"]))
        except json.JSONDecodeError:
            return {"intent": session["summary"][:200], "conclusion": "无", "todos": [], "preferences": []}

    def cleanup_expired(self) -> None:
        """删除超过 SESSION_EXPIRE_HOURS 的过期会话摘要。"""
        try:
            cutoff = (
                __import__("datetime").datetime.now()
                - __import__("datetime").timedelta(hours=get_settings().SESSION_EXPIRE_HOURS)
            ).isoformat()
            self._sqlite.conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            self._sqlite.conn.commit()
        except Exception as e:
            logger.warning("MidTerm cleanup_expired failed: %s", e)

    def get_sessions_in_range(self, start: str, end: str) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        try:
            rows = self._sqlite.conn.execute(
                "SELECT * FROM sessions WHERE created_at >= ? AND created_at <= ? ORDER BY created_at", (start, end)
            ).fetchall()
            for row in rows:
                s: dict[str, Any] = dict(row)
                if s.get("summary"):
                    with suppress(json.JSONDecodeError):
                        s["summary"] = json.loads(s["summary"])
                sessions.append(s)
        except Exception as e:
            logger.warning("Session range query failed: %s", e)
        result_list: list[dict[str, Any]] = sessions
        return result_list


_mid_instance: MidTermMemory | None = None


def get_mid_term_memory(sqlite_client: SQLiteClient, model_adapter: ModelAdapter | None = None) -> MidTermMemory:
    global _mid_instance
    if _mid_instance is None:
        _mid_instance = MidTermMemory(sqlite_client, model_adapter)
    return _mid_instance

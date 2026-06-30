"""ToolRegistry 工具注册中心 -- 线程安全 + get_schema。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)
ToolFunc = Callable[..., Coroutine[Any, Any, str]]


class ToolRegistry:
    """工具注册中心，集中管理所有工具的生命周期。线程安全。"""

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register(self, name: str, description: str, func: ToolFunc, parameters: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._tools[name] = {
                "name": name,
                "description": description,
                "func": func,
                "parameters": parameters or {"type": "object", "properties": {}},
            }
            logger.info("Tool registered: %s", name)

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info("Tool unregistered: %s", name)
                return True
            logger.warning("Tool not found for unregister: %s", name)
            return False

    def get_func(self, name: str) -> ToolFunc | None:
        with self._lock:
            tool = self._tools.get(name)
            return tool["func"] if tool else None

    def get_schema(self, name: str) -> dict[str, Any]:
        """获取工具 JSON Schema。
        Raises:
            KeyError: 工具不存在时抛出。
        """
        with self._lock:
            if name not in self._tools:
                raise KeyError(f"Tool '{name}' not registered")
            t = self._tools[name]
            return {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }

    def list_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
                for t in self._tools.values()
            ]

    def remove_disabled(self, disabled_names: list[str]) -> int:
        count = 0
        for name in disabled_names:
            if self.unregister(name):
                count += 1
        return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)


_registry_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance

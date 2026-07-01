"""启动环境变量强校验 -- 含测试旁路开关。"""

from __future__ import annotations

import sys

from config.settings import get_settings

_TEST_MODE: bool = False

REQUIRED_VARS: list[tuple[str, str]] = [
    ("LLM_DEEPSEEK_API_KEY", "DeepSeek 主模型 API Key"),
    ("LLM_DOUBAO_API_KEY", "豆包兜底模型 API Key"),
    ("TAVILY_API_KEY", "Tavily 联网搜索 API Key"),
]


def set_test_mode(enabled: bool = True) -> None:
    global _TEST_MODE
    _TEST_MODE = enabled


def validate_env() -> list[str]:
    if _TEST_MODE:
        return []
    s = get_settings()
    missing: list[str] = []
    for var_name, desc in REQUIRED_VARS:
        val = getattr(s, var_name, "")
        if not val or val.startswith("your-"):
            missing.append(f"  - {var_name}: {desc}")
    return missing


def validate_or_exit() -> None:
    missing = validate_env()
    if missing:
        print("错误: 以下必填环境变量缺失:\n" + "\n".join(missing))
        print("请复制 .env.example 为 .env 并填写真实值")
        sys.exit(1)

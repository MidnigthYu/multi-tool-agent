"""Streamlit 双栏可视化前端入口 — v0.8.0-frontend。

工业级双栏布局：
- 左侧边栏：会话管理、工具开关、参数配置、周报生成
- 右侧主面板：聊天界面、ReAct 链路可视化（思考/工具调用折叠展示）

架构约束：core/ tools/ storage/ memory/ config/ api/ 零变更，
全部 Agent 逻辑复用 v0.7.0-weekly 基线。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

# === 页面配置 ===
st.set_page_config(
    page_title="多工具智能助理 v0.8.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === 全局单例缓存：避免每次 rerun 重复初始化 Agent / MemoryManager ===


@st.cache_resource
def _get_cached_agent() -> Any:
    """缓存 Agent 编译图单例，避免重复初始化 LLM / 工具注册 / 向量库。"""
    from frontend.session_manager import SessionManager

    return SessionManager.get_cached_agent()


@st.cache_resource
def _get_cached_memory_manager() -> Any:
    """缓存 MemoryManager 单例，避免重复初始化 SQLite / ChromaDB 连接。"""
    from frontend.session_manager import SessionManager

    return SessionManager.get_cached_memory_manager()


@st.cache_resource
def _get_cached_session_manager() -> Any:
    """缓存 SessionManager 单例，持久化会话列表。"""
    from frontend.session_manager import SessionManager

    return SessionManager()


# === 会话初始化 ===
if "session_id" not in st.session_state:
    sm = _get_cached_session_manager()
    state = sm.create_session()
    st.session_state.session_id = state.session_id
    st.session_state.messages = []
    st.session_state.tools_disabled = []
    st.session_state.short_term_max_messages = 5
    st.session_state.max_reflection_rounds = 2

# === 工具列表（从 ToolRegistry 动态获取） ===
def _get_available_tools() -> list[dict[str, Any]]:
    """获取当前注册的全部工具元数据。"""
    from core.tool_registry import get_tool_registry

    return get_tool_registry().list_tools()


AVAILABLE_TOOLS = _get_available_tools()
TOOL_LABELS: dict[str, str] = {
    "web_search": "🌐 联网搜索",
    "code_executor": "💻 代码沙箱",
    "index_documents": "📄 文档索引",
    "knowledge_search": "🔍 知识库检索",
    "remember_this": "🧠 记忆写入",
    "weekly_report": "📊 周报生成",
}


# === 工具开关联动：将取消勾选的工具同步到 tools_disabled ===
def _sync_tools_disabled() -> None:
    """根据 checkboxes 状态更新 tools_disabled 列表。"""
    disabled: list[str] = []
    for tool in AVAILABLE_TOOLS:
        name = tool["name"]
        key = f"tool_{name}"
        if key in st.session_state and not st.session_state[key]:
            disabled.append(name)
    st.session_state.tools_disabled = disabled


# === 侧边栏 ===
with st.sidebar:
    st.header("🤖 多工具智能助理")
    st.caption("v0.8.0-frontend")

    # --- 会话管理 ---
    st.subheader("📂 会话管理")
    sm = _get_cached_session_manager()

    col_new, col_del = st.columns([2, 1])
    with col_new:
        if st.button("➕ 新建会话", use_container_width=True):
            state = sm.create_session()
            st.session_state.session_id = state.session_id
            st.session_state.messages = []
            st.session_state.tools_disabled = []
            st.rerun()
    with col_del:
        if st.button("🗑️", help="删除当前会话"):
            current_sid = st.session_state.session_id
            sm.remove_session(current_sid)
            sessions = sm.list_sessions()
            if sessions:
                new_state = sessions[0]
                st.session_state.session_id = new_state.session_id
            else:
                new_state = sm.create_session()
                st.session_state.session_id = new_state.session_id
            st.session_state.messages = []
            st.session_state.tools_disabled = []
            st.rerun()

    # 会话列表
    sessions = sm.list_sessions()
    if len(sessions) > 1:
        session_options = {s.session_id: f"{s.name} ({s.session_id})" for s in sessions}
        selected_sid = st.selectbox(
            "切换会话",
            options=list(session_options.keys()),
            format_func=lambda sid: session_options[sid],
            index=(
                list(session_options.keys()).index(st.session_state.session_id)
                if st.session_state.session_id in session_options
                else 0
            ),
        )
        if selected_sid != st.session_state.session_id:
            st.session_state.session_id = selected_sid
            st.session_state.messages = []
            st.rerun()

    # 当前会话信息
    current_s = sm.get_session(st.session_state.session_id)
    if current_s:
        st.caption(f"🆔 会话 ID: `{current_s.session_id}`")
        st.caption(f"🕐 创建时间: {current_s.created_at[:19]}")

    st.divider()

    # --- 工具开关 ---
    st.subheader("🔧 工具开关")
    st.caption("取消勾选将在当前会话中禁用该工具")

    for tool in AVAILABLE_TOOLS:
        name = tool["name"]
        label = TOOL_LABELS.get(name, name)
        key = f"tool_{name}"
        # 初始化 checkbox 状态：若 key 不存在则默认勾选
        if key not in st.session_state:
            st.session_state[key] = name not in st.session_state.tools_disabled
        st.checkbox(
            label,
            key=key,
            on_change=_sync_tools_disabled,
            help=tool.get("description", ""),
        )
    # 首次加载时同步一次
    _sync_tools_disabled()

    st.divider()

    # --- 参数配置 ---
    st.subheader("⚙️ 参数配置")

    short_term_val = st.slider(
        "短期记忆窗口",
        min_value=1,
        max_value=20,
        value=st.session_state.short_term_max_messages,
        step=1,
        help="控制 Agent 每次携带的最近消息数量",
    )
    st.session_state.short_term_max_messages = short_term_val

    st.session_state.max_reflection_rounds = st.slider(
        "最大反思轮次",
        min_value=0,
        max_value=5,
        value=st.session_state.max_reflection_rounds,
        step=1,
        help="工具执行失败后的最大重试反思次数",
    )

    st.divider()

    # --- 操作区 ---
    st.subheader("⚡ 快捷操作")

    if st.button("📊 一键生成周报", use_container_width=True):
        with st.spinner("正在生成周报..."):
            from importlib import import_module, reload

            mod = import_module("frontend.agent_runner")
            reload(mod)
            run_agent_sync = mod.run_agent_sync

            sid = st.session_state.session_id
            result = run_agent_sync(
                sid,
                "请根据当前会话生成周报",
                state_overrides={
                    "tools_disabled": [
                        t for t in st.session_state.tools_disabled if t != "weekly_report"
                    ]
                },
            )
            if not result["error"]:
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result["reply"],
                        "metadata": {
                            "tool_calls": result["tool_calls"],
                            "tool_results": result["tool_results"],
                            "observability": result["observability"],
                        },
                    }
                )
        st.rerun()

    if st.button("🗑️ 清空当前对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # --- 状态栏 ---
    st.caption(f"💬 消息数: {len(st.session_state.messages)}")
    st.caption(f"🚫 禁用工具: {len(st.session_state.tools_disabled)}")


# === 主面板：聊天界面 ===
st.title("🤖 多工具智能助理")

# 渲染历史消息
for _idx, msg in enumerate(st.session_state.messages):
    role = msg["role"]
    content = msg.get("content", "")
    metadata = msg.get("metadata") if role == "assistant" else None

    with st.chat_message(role):
        st.markdown(content)

        # ReAct 链路可视化（仅 assistant 消息且有工具调用时展示）
        if metadata:
            tool_calls = metadata.get("tool_calls", [])
            tool_results = metadata.get("tool_results", {})
            observability = metadata.get("observability", {})

            if tool_calls:
                with st.expander("🔧 工具调用详情", expanded=False):
                    for tc in tool_calls:
                        tool_name = tc.get("tool", "unknown")
                        params = tc.get("params", {})
                        status = tc.get("status", "pending")
                        status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
                        st.markdown(f"{status_icon} **{tool_name}** — `{status}`")
                        if params:
                            st.caption(f"参数: {str(params)[:300]}")

            if tool_results:
                with st.expander("📊 工具返回结果", expanded=False):
                    for tname, tresult in tool_results.items():
                        st.markdown(f"**{tname}**")
                        result_str = str(tresult)
                        if len(result_str) > 500:
                            st.text(result_str[:500] + "\n... [内容已截断]")
                        else:
                            st.text(result_str)

            if observability.get("node_timings"):
                with st.expander("⏱️ 节点耗时", expanded=False):
                    timings = observability["node_timings"]
                    for node_name, elapsed_ms in timings.items():
                        bar_len = min(int(elapsed_ms / 10), 40)
                        bar = "█" * bar_len
                        st.caption(f"`{node_name}`: {bar} {elapsed_ms}ms")

            error_list = observability.get("errors", [])
            if error_list:
                with st.expander("⚠️ 异常信息", expanded=bool(error_list)):
                    for err in error_list:
                        st.warning(f"[{err.get('code', 'UNKNOWN')}] {err.get('detail', str(err))}")

# === 聊天输入 ===
user_input = st.chat_input("输入消息...")

if user_input:
    # 用户消息追加到历史
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 调用 Agent
    with st.spinner("思考中..."):
        from importlib import import_module, reload

        mod = import_module("frontend.agent_runner")
        reload(mod)
        run_agent_sync = mod.run_agent_sync

        sid = st.session_state.session_id
        result = run_agent_sync(
            sid,
            user_input,
            state_overrides={
                "tools_disabled": st.session_state.tools_disabled,
            },
        )

    # 助手回复追加到历史（含元数据用于 ReAct 可视化）
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result["reply"],
            "metadata": {
                "tool_calls": result["tool_calls"],
                "tool_results": result["tool_results"],
                "observability": result["observability"],
            },
        }
    )

    st.rerun()

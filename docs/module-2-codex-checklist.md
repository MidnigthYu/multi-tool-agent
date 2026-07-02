# 模块2 Codex 任务清单

> **源设计文档**: `docs/module-2-design.md`
> **基线**: v0.2.1-bugfix | 202 用例 0 失败 | 覆盖率 96.73%
> **执行方式**: 逐项执行，每完成一项打 ✅，遇到阻塞标注 🚫 并说明原因

---

## Task 1: `tools/search_tool.py` — 搜索工具完整实现

### 1.1 新增 `SearchInput` Pydantic Schema

- [ ] 在文件顶部从 `pydantic` 导入 `BaseModel, Field`
- [ ] 定义 `class SearchInput(BaseModel)`:
  - `query: str = Field(..., min_length=1)` — 搜索查询词
  - `max_results: int = Field(default=5, ge=1, le=10)` — 最大返回条数
  - `search_depth: str = Field(default="advanced")` — basic / advanced
- [ ] 添加 Google 风格 docstring: `"""搜索工具入参 Pydantic Schema，适配 ToolRegistry 注册规范。"""`

**验证**: `python -c "from tools.search_tool import SearchInput; s=SearchInput(query='test'); print(s.model_dump())"` 输出 `{'query': 'test', 'max_results': 5, 'search_depth': 'advanced'}`

---

### 1.2 新增 `_classify_search_error` 异常分类函数

- [ ] 函数签名: `def _classify_search_error(exc: Exception) -> str`
- [ ] 从 `str(exc).lower()` 匹配关键字，返回分类标签:
  - `"timeout"` ← `timeout` / `timed out` / `connect timeout`
  - `"network"` ← `connection` / `network` / `refused` / `unreachable`
  - `"rate_limit"` ← `rate` / `limit` / `429` / `too many`
  - `"auth"` ← `auth` / `key` / `unauthorized` / `401` / `403`
  - 默认 → `"unknown"`
- [ ] 添加 docstring: `"""分类搜索异常类型，用于结构化日志埋点。Returns: timeout/network/rate_limit/auth/unknown"""`

**验证**: `python -c "from tools.search_tool import _classify_search_error; print(_classify_search_error(TimeoutError('timed out')))"` 输出 `timeout`

---

### 1.3 重写 `web_search` — 增强日志 + 新增返回字段

**保持现有函数签名不变**: `async def web_search(query: str, max_results: int = 5, search_depth: str = "advanced") -> dict[str, Any]`

- [ ] 函数开头记录 `t_start = time.monotonic()`
- [ ] **Layer 0: API Key 校验**
  - 检查 `not api_key or api_key.startswith("your-") or api_key.startswith("test-")`
  - 命中时: WARNING 日志 → 直接返回降级 dict（含 `elapsed_ms` 字段），不进入重试
  - 降级 formatted: `"[搜索降级] 搜索服务未配置，请设置 TAVILY_API_KEY。我将基于已有知识回答您的问题。"`
- [ ] **Layer 1: Tavily API 调用 + 重试循环**
  - `for attempt in range(settings.SEARCH_RETRY_MAX + 1):`
  - 成功 → `break`
  - 失败 → `retry_count = attempt + 1` → `_classify_search_error(e)` → WARNING 日志（含 err_type）→ `asyncio.sleep(delay)` → continue
  - `for-else` 全部失败 → `raise last_exc`
- [ ] **成功路径**:
  - 解析 `data["results"]`，每个 item 提取 `title/content/snippet/url`
  - `content` 经 `_truncate_result` 截断
  - 构造 `formatted` 字符串: `【搜索结果】查询：<query>\n1. <title>\n   <snippet>\n   URL: <url>...`
  - INFO 日志: `[search_tool] Success | query=<截断100> | results=<N> | retries=<N> | elapsed=<N>ms`
  - 返回 dict 必须包含 6 个 key: `status`, `query`, `results`, `formatted`, `retry_count`, `elapsed_ms`
- [ ] **Layer 2: 最外层异常捕获**
  - `except Exception as e:` — ERROR 日志含 query/err_type/retries/elapsed_ms/exc
  - 返回降级 dict: `status="failed"`, `formatted="[搜索降级] 搜索暂时不可用，请稍后重试。我将基于已有知识回答您的问题。"`

**日志格式强制约束** (严格匹配):
```
[search_tool] TAVILY_API_KEY not configured | query=<截断>
[search_tool] Retry 1/2 after 1.0s | query=<截断> | err_type=timeout | exc=...
[search_tool] Success | query=<截断> | results=5 | retries=0 | elapsed=234ms
[search_tool] Failed | query=<截断> | err_type=network | retries=2 | elapsed=3123ms | exc=...
```

---

### 1.4 新增 `search_tool` — ToolRegistry 兼容封装

- [ ] 函数签名: `async def search_tool(query: str, max_results: int = 5, search_depth: str = "advanced") -> str`
- [ ] 内部调用 `result = await web_search(query, max_results, search_depth)`
- [ ] 返回 `result["formatted"]`（纯文本字符串）
- [ ] docstring 注明: `"""ToolRegistry 兼容封装...故障完全隔离..."""`

**验证**: `python -c "import asyncio; from tools.search_tool import search_tool; print(type(asyncio.run(search_tool('test'))))"` → 需要 mock Tavily key 或接受降级输出为 `<class 'str'>`

---

### 1.5 保留函数（不修改）

- [ ] `_truncate_result(raw_text, max_chars=4000)` — 保持原样
- [ ] `_retry_with_backoff(func, max_retries=2, base_delay=1.0)` — 保持原样，添加注释 `"""同步指数退避重试，保留用于向后兼容。"""`

### 1.6 更新 `__all__`

- [ ] `__all__ = ["SearchInput", "search_tool", "web_search", "_retry_with_backoff", "_truncate_result"]`

### 1.7 更新 `tools/__init__.py`

- [ ] `from tools.search_tool import SearchInput, search_tool, web_search`
- [ ] `__all__ = ["SearchInput", "search_tool", "web_search"]`

---

## Task 2: `tests/test_tools/test_search_tool.py` — 全套单元测试

### 2.1 导入

- [ ] 从 `tools.search_tool` 导入全部 6 个公开符号
- [ ] `from unittest.mock import AsyncMock, MagicMock, patch`
- [ ] `import pytest`

### 2.2 TestWebSearch — web_search 内核 (22 用例)

| # | 测试方法 | 断言 |
|---|---------|------|
| 1 | `test_normal_query` | `r["status"] == "success" and len(r["results"]) == 1` |
| 2 | `test_empty_query` | `r["status"] == "success" and r["results"] == []` |
| 3 | `test_timeout_retry` | `r["status"] == "failed"` |
| 4 | `test_network_disconnect` | `r["status"] == "failed"` + `"降级" in r["formatted"] or "搜索" in r["formatted"]` |
| 5 | `test_rate_limit` | `r["status"] == "failed"` + 降级文案检查 |
| 6 | `test_missing_api_key_your_prefix` | key=`"your-api-key-here"` → `"failed"` + `"API" in r["formatted"]` |
| 7 | `test_empty_api_key` | key=`""` → `"failed"` |
| 8 | `test_test_prefix_key` | key=`"test-fake-key-12345"` → `"failed"` |
| 9 | `test_truncation` | `_truncate_result("A"*5000, 100)` → `len(t) < 5000 and "..." in t` |
| 10 | `test_no_truncation` | `_truncate_result("Hello", 100) == "Hello"` |
| 11 | `test_max_results` | mock 返回 20 条, `max_results=3` → `len(r["results"]) == 3` |
| 12 | `test_formatted_contains_query` | `"hello world" in r["formatted"]` |
| 13 | `test_formatted_numbered` | `"1." in r["formatted"] and "2." in r["formatted"]` |
| 14 | `test_has_status_field` | 6 个 key 全部存在: `status, query, results, formatted, retry_count, elapsed_ms` |
| 15 | `test_search_depth` | `inst.search.call_args.kwargs.get("search_depth") == "basic"` |
| 16 | `test_retry_then_success` | `side_effect=[TimeoutError, {...}]` → `r["status"]=="success"` + `r["retry_count"] >= 1` |
| 17 | `test_snippet_fallback` | content=`""` → `r["results"][0]["snippet"] == ""` |
| 18 | `test_special_chars` | query=`"test + query #1"` → `r["status"]=="success"` |
| 19 | `test_formatted_has_url` | URL 出现在 formatted 中 |
| 20 | `test_default_max_results` | 不传 max_results, mock 返回 10 条 → `len(r["results"]) <= 5` |
| 21 | `test_elapsed_ms_field` | `isinstance(r["elapsed_ms"], int) and r["elapsed_ms"] >= 0` |
| 22 | `test_retry_count_on_success` | 首次成功 → `r["retry_count"] == 0` |

- [ ] 全部 22 个用例通过 `@pytest.mark.asyncio` 标记
- [ ] 每个用例用 `with patch("tools.search_tool.AsyncTavilyClient")` 模拟 Tavily
- [ ] API key 类用例用 `with patch("tools.search_tool.get_settings")` 旁路

### 2.3 TestSearchTool — 封装层 (3 用例)

| # | 测试方法 | 断言 |
|---|---------|------|
| 1 | `test_returns_string` | `isinstance(result, str)` + 内容包含 query |
| 2 | `test_returns_degraded_on_failure` | 超时时返回 str + `"降级" in result` |
| 3 | `test_passes_max_results` | `max_results=3` → formatted 包含 1/2/3 序号 |

### 2.4 TestSearchInput — Schema (5 用例)

| # | 测试方法 | 断言 |
|---|---------|------|
| 1 | `test_valid_input` | 构造成功，字段值匹配 |
| 2 | `test_default_values` | `max_results==5, search_depth=="advanced"` |
| 3 | `test_empty_query_rejected` | `SearchInput(query="")` → `pytest.raises(Exception)` |
| 4 | `test_max_results_cap` | `max_results=10` 通过 |
| 5 | `test_max_results_exceeded_rejected` | `max_results=11` → `pytest.raises(Exception)` |

### 2.5 TestClassifySearchError — 异常分类 (7 用例)

| # | 输入异常 | 预期输出 |
|---|---------|---------|
| 1 | `TimeoutError("Connection timed out")` | `"timeout"` |
| 2 | `ConnectionRefusedError("Connection refused")` | `"network"` |
| 3 | `Exception("429 Too Many Requests")` | `"rate_limit"` |
| 4 | `Exception("rate limit exceeded")` | `"rate_limit"` |
| 5 | `Exception("401 Unauthorized")` | `"auth"` |
| 6 | `Exception("Invalid API key")` | `"auth"` |
| 7 | `Exception("something weird happened")` | `"unknown"` |

### 2.6 TestRetryWithBackoff — 遗留重试 (3 用例)

| # | 测试方法 | 断言 |
|---|---------|------|
| 1 | `test_success_first_attempt` | 返回 `"ok"`, 仅调用 1 次 |
| 2 | `test_retry_then_success` | 失败 2 次后成功 → 返回 `"recovered"` + `mock_sleep.call_count == 2` |
| 3 | `test_all_retries_fail` | `pytest.raises(ValueError, match="always fail")` |

### 2.7 验证命令

```bash
python -m pytest tests/test_tools/test_search_tool.py -v          # 全部 PASS
python -m pytest tests/test_tools/test_search_tool.py --cov=tools.search_tool --cov-report=term  # 新增代码 100%
```

---

## Task 3: `core/router_node.py` — ReAct 路由 Prompt 增强

### 3.1 更新 `ROUTER_PROMPT`

- [ ] 替换为增强版 Prompt（见下方），关键字:
  - **direct_reply** 明确列出: 闲聊、问候、自我介绍、主观意见、已有工具结果
  - **tool_dispatch** 明确列出: 实时/时效性信息、未知外部知识、事实查询、联网验证
  - **end_conversation** 仅用户明确结束
  - 输出格式不变: `{"action": "...", "reason": "...", "selected_tools": [...]}`
  - `selected_tools` 仅在 `action=tool_dispatch` 时填 `["web_search"]`

- [ ] **不做修改**的部分:
  - `router_node()` 函数体逻辑（快速路径 + LLM 调用 + JSON 解析 + 默认 fallback）
  - `direct_reply_node()` 函数体逻辑
  - `should_continue()` 条件边映射

**新 ROUTER_PROMPT**:
```python
ROUTER_PROMPT = (
    "你是一个智能路由判断系统。根据用户输入和历史对话，判断下一步行动。\n\n"
    "## 路由规则\n"
    "1. **direct_reply**: 以下情况直接由 LLM 生成回复，不需要调用工具：\n"
    '   - 闲聊、问候（如"你好""今天天气真好"）\n'
    '   - 自我介绍类问题（如"你是谁""你能做什么"）\n'
    '   - 纯主观意见/建议（如"你觉得怎么样""给我推荐"）\n'
    "   - 已有工具结果需要整合回复时（由系统自动路由）\n\n"
    "2. **tool_dispatch**: 以下情况必须调用工具获取外部信息：\n"
    '   - 需要实时/时效性信息（如"今天天气""最新新闻""现在股价"）\n'
    '   - 需要未知/不确定的外部知识（如"什么是XX""XX是什么意思"）\n'
    '   - 需要搜索/查询具体事实（如"2024年奥运会金牌榜"）\n'
    "   - 需要联网验证的信息\n\n"
    "3. **end_conversation**: 用户明确表示结束对话时才使用。\n\n"
    "## 输出格式\n"
    "严格输出以下 JSON，不要添加任何其他内容：\n"
    '{"action": "direct_reply|tool_dispatch|end_conversation", '
    '"reason": "不超过20字的判断理由", "selected_tools": []}\n\n'
    "注意: selected_tools 仅在 action=tool_dispatch 时填写工具名列表（如 [\"web_search\"]），其他情况为空数组。"
)
```

### 3.2 验证命令

```bash
python -m pytest tests/test_core/test_router_node.py -v  # 全部 PASS（确认不破坏现有路由测试）
```

---

## Task 4: `core/agent_graph.py` — 图节点集成改造

### 4.1 改造 `_tool_dispatch_node` — 参数提取

**位置**: `build_agent_graph()` 内部函数

**改造前** (当前代码):
```python
tcs = [{"tool": t, "params": {}, "status": "pending"} for t in state.get("selected_tools", [])]
```

**改造后**:
```python
# 从消息历史提取用户问题作为搜索参数
messages = state.get("messages", [])
user_query = ""
for m in reversed(messages):
    content = m.content if hasattr(m, "content") else str(m)
    if isinstance(content, str) and content.strip():
        user_query = content
        break

tcs = []
for t in state.get("selected_tools", []):
    params: dict[str, Any] = {}
    if t == "web_search":
        params = {"query": user_query}
    tcs.append({"tool": t, "params": params, "status": "pending"})
```

**约束**:
- 仅 `"web_search"` 工具提取 query 参数
- 其他工具保持 `params = {}`（向后兼容）
- query 不做语义加工，原样传递最后一条有内容的用户消息

---

### 4.2 改造 `_tool_execute_node` — 防御 dict 返回值

**位置**: `build_agent_graph()` 内部函数

**改造后异步路径**:
```python
if asyncio.iscoroutine(maybe_coro):
    raw = await maybe_coro
    if isinstance(raw, dict):
        tool_output: str = raw.get("formatted", str(raw))
    else:
        tool_output = str(raw)
```

**改造后同步路径**:
```python
else:
    if isinstance(maybe_coro, dict):
        tool_output = maybe_coro.get("formatted", str(maybe_coro))
    else:
        tool_output = str(maybe_coro)
```

**约束**: 不修改 `ToolRegistry` 类型签名，仅在节点层面做防御式兼容。

---

### 4.3 改造 `_result_integration_node` — 防御 dict 值

**位置**: `build_agent_graph()` 内部函数

**改造前** (当前代码):
```python
errors = [k for k, v in tr.items() if "错误" in v or "未注册" in v]
```

**改造后**:
```python
errors = []
for k, v in tr.items():
    if isinstance(v, str):
        if "错误" in v or "未注册" in v:
            errors.append(k)
    # elif isinstance(v, dict):
    #     # dict 类型结果视为无硬错误（业务降级已在工具层闭环）
    #     pass
```

**设计理由**: dict 类型值已在工具内部完成业务降级，不触发 reflection 重试。

---

### 4.4 改造 `get_agent()` — 自动注册 search_tool

**位置**: 模块级函数

**改造后**:
```python
def get_agent() -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    global _compiled_agent
    if _compiled_agent is None:
        from core.model_adapter import get_model_adapter
        from core.tool_registry import get_tool_registry
        from tools import search_tool, SearchInput

        reg = get_tool_registry()
        # 幂等注册：仅在未注册时执行
        if "web_search" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                name="web_search",
                description=(
                    "Tavily 联网搜索工具 — 搜索互联网获取实时信息、新闻、百科知识。"
                    "适用场景：需要时效性信息、未知外部知识、事实查询。"
                ),
                func=search_tool,  # type: ignore[arg-type]
                parameters=SearchInput.model_json_schema(),
            )

        _compiled_agent = build_agent_graph(get_model_adapter(), reg)
    return _compiled_agent
```

---

### 4.5 更新 `main()` 函数

**位置**: `main()` 函数内

- [ ] 删除 `main()` 中手动的 `reg.register("web_search", ...)` 调用（已由 `get_agent()` 自动完成）
- [ ] `from tools import web_search` 改为 `from tools import search_tool`（如果不再直接使用 web_search）

### 4.6 不修改清单（确认无改动）

- [ ] 7 个 `add_node` 调用 — 不修改
- [ ] 2 个固定边 (`direct_reply→memory_update`, `tool_dispatch→tool_execute`, `tool_execute→result_integration`, `memory_update→END`) — 不修改
- [ ] 3 个条件边 (`preprocess`, `router`, `result_integration`) — 不修改
- [ ] `MemorySaver(checkpointer)` — 不修改
- [ ] `_preprocess_node`, `_router_node`, `_direct_reply_node`, `_memory_update_node` — 不修改

### 4.7 验证命令

```bash
python -m pytest tests/test_core/test_agent_graph.py -v  # 全部 PASS
```

---

## Task 5: 全量门禁

### 5.1 执行顺序（不可颠倒）

```bash
# 1. Ruff 格式化检查
python -m ruff format --check .

# 2. Ruff Lint
python -m ruff check .

# 3. Mypy 严格类型检查
python -m mypy --strict .

# 4. 全量 Pytest + 覆盖率
python -m pytest tests/ -v --cov=. --cov-report=term --cov-fail-under=90
```

### 5.2 通过标准

| 检查项 | 标准 | 不达标处理 |
|--------|------|-----------|
| ruff format | 零差异 | 执行 `ruff format .` 后重新检查 |
| ruff check | 零报错 | 逐条修复，不做 `--fix` 批量忽略 |
| mypy --strict | 零报错 | 修复类型注解，不在 `pyproject.toml` 放宽规则 |
| pytest | 全量 0 失败 | 修复失败的测试或确认是已存在的基线失败 |
| coverage | ≥ 90% | 补充缺失的测试用例 |

### 5.3 覆盖率报告解读

- 如果 `tools/search_tool.py` 的 `assert last_exc is not None` 行被标记为未覆盖 → 正常（逻辑不可达防御代码），如需排除可加 `# pragma: no cover`
- 如果已有模块覆盖率下降 → **阻塞**，必须在当前 PR 中修复

---

## 变更文件总览

| 文件 | 操作 | 风险等级 |
|------|------|---------|
| `tools/search_tool.py` | 重写 | 🟡 中 — 核心新功能 |
| `tools/__init__.py` | 更新导出 | 🟢 低 |
| `tests/test_tools/test_search_tool.py` | 重写 | 🟡 中 — 35 新用例 |
| `core/router_node.py` | 仅改 ROUTER_PROMPT 常量 | 🟢 低 |
| `core/agent_graph.py` | 修改 3 个内部函数 + get_agent + main | 🔴 高 — 图调度核心 |

**禁止触碰的文件** (16 个):
`agent_state.py`, `model_adapter.py`, `tool_registry.py`, `exceptions.py`, `logger.py`, `settings.py`, `constants.py`, `error_codes.py`, `env_validator.py`, `startup.py`, `memory/*`, `storage/*`, `api/*`, `frontend/*`, 以及 tests/ 下除 `test_tools/test_search_tool.py` 外的所有文件。

---

## Commit 模板

```
feat(module-2): Tavily 联网搜索工具 + ReAct 路由增强

## 新增
- SearchInput Pydantic 入参 Schema (query/max_results/search_depth)
- search_tool ToolRegistry 兼容封装 (返回 str)
- _classify_search_error 异常分类函数 (timeout/network/rate_limit/auth/unknown)
- web_search 增强: retry_count/elapsed_ms 字段 + 结构化日志埋点

## 修复
- _tool_dispatch_node: 从 messages 提取 query 参数，修复空 params 导致搜索工具调用失败
- _tool_execute_node: 防御式处理 dict 返回值
- _result_integration_node: 防御式处理 dict 值检查

## 路由
- ROUTER_PROMPT 增强: 明确闲聊/搜索场景判断规则

## 测试
- test_search_tool.py: 40 用例 (TestWebSearch 22 + TestSearchTool 3 + TestSearchInput 5 + TestClassifySearchError 7 + TestRetryWithBackoff 3)
- 新增代码覆盖率 100%

## 门禁
- ruff format --check: PASS
- ruff check: PASS
- mypy --strict: PASS
- pytest: 全量 PASS
- coverage: ≥ 90%

Co-Authored-By: Claude <noreply@anthropic.com>
```

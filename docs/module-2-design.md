# 模块2 Tavily 联网搜索 + ReAct 路由 — 方案设计文档

> **基线**: v0.2.1-bugfix | 202 用例 0 失败 | 覆盖率 96.73% | ruff/mypy 零报错
> **交付对象**: Codex 代码落地
> **设计原则**: 不新增抽象层、不改动已有业务底层逻辑、所有异常在工具层闭环

---

## 1. 模块整体架构流程

```
┌──────────────────────────────────────────────────────────────────┐
│                     LangGraph ReAct 闭环                          │
│                                                                  │
│   User Input                                                     │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────┐    空消息/missing     ┌─────┐                      │
│  │preprocess│ ────────────────────► │ END │                      │
│  └────┬─────┘                       └─────┘                      │
│       │ 正常                                                      │
│       ▼                                                          │
│  ┌──────────┐                                                    │
│  │  router  │ ◄────────────────────────────────┐                 │
│  │ (LLM决策)│                                   │                 │
│  └────┬─────┘                                   │                 │
│       │                                         │                 │
│   ┌───┼──────────────────┐                      │                 │
│   │   │                   │                      │                 │
│   ▼   ▼                   ▼                      │                 │
│ direct  tool          end_conversation           │                 │
│ _reply  _dispatch         │                      │                 │
│   │       │               │                      │                 │
│   │       ▼               │                      │                 │
│   │  ┌──────────┐         │                      │                 │
│   │  │  tool    │         │                      │                 │
│   │  │ _execute │         │                      │                 │
│   │  │(search)  │         │                      │                 │
│   │  └────┬─────┘         │                      │                 │
│   │       │               │                      │                 │
│   │       ▼               │                      │                 │
│   │  ┌──────────────┐     │                      │                 │
│   │  │   result     │     │                      │                 │
│   │  │ _integration │─────┼── 有错误且可重试 ─────┘                 │
│   │  └──────┬───────┘     │    (reflection)                       │
│   │         │ 无错误      │                                       │
│   │         ▼             │                                       │
│   └────►┌──────────┐      │                                       │
│         │ memory   │◄─────┘                                       │
│         │ _update  │                                              │
│         └────┬─────┘                                              │
│              ▼                                                    │
│            END                                                    │
└──────────────────────────────────────────────────────────────────┘
```

**数据流关键路径**:

| 场景 | 路径 | 触发条件 |
|------|------|----------|
| 闲聊/自我介绍 | preprocess → router → direct_reply → memory_update → END | LLM 判断 `action=direct_reply` |
| 时效性/外部知识 | preprocess → router → tool_dispatch → tool_execute → result_integration → memory_update → END | LLM 判断 `action=tool_dispatch`, `selected_tools=["web_search"]` |
| 工具失败重试 | result_integration → router (reflection) | `needs_reflection=True` 且 `reflection_count < MAX_REFLECTION_ROUNDS` |

---

## 2. search_tool 分层设计

### 2.1 分层架构

```
┌─────────────────────────────────────┐
│          ToolRegistry 层             │
│  search_tool(query, ...) → str      │  ← 符合 ToolRegistry 签名规范
│  故障完全隔离，永不抛异常              │     func(**params) → Coroutine[Any,Any,str]
└──────────────┬──────────────────────┘
               │ 调用
┌──────────────▼──────────────────────┐
│          业务内核层                    │
│  web_search(query, ...) → dict      │  ← 程序化调用接口
│  返回结构化 dict: status/query/      │     {"status","query","results",
│  results/formatted/retry_count/      │      "formatted","retry_count",
│  elapsed_ms                          │      "elapsed_ms"}
└──────────────┬──────────────────────┘
               │ 组装
┌──────────────▼──────────────────────┐
│          功能原子层                    │
│  _truncate_result()     结果截断      │
│  _classify_search_error() 异常分类    │
│  _retry_with_backoff()   同步重试     │  ← 遗留兼容函数
└─────────────────────────────────────┘
```

### 2.2 异步封装规则

- 使用 `tavily.AsyncTavilyClient`，全链路 `async/await`
- 客户端每次调用现场构造 `AsyncTavilyClient(api_key=api_key)`，不复用连接（避免会话级故障传播）
- `search_tool` 封装层将 `web_search` 返回的 `dict["formatted"]` 提取为纯文本字符串返回

### 2.3 指数退避重试策略

| 参数 | 来源 | 值 |
|------|------|-----|
| `max_retries` | `settings.SEARCH_RETRY_MAX` | 2 |
| `base_delay` | `settings.SEARCH_RETRY_BASE_DELAY_S` | 1s |
| 退避公式 | `base_delay × 2^attempt` | 1s → 2s |
| 总重试窗口 | 最坏情况 | ~3s (1s + 2s) |

**重试覆盖的异常类型**（不区分异常类型，全部重试）:
- `TimeoutError` / `asyncio.TimeoutError`
- `ConnectionError` / `ConnectionRefusedError`
- `OSError`（网络不可达）
- Tavily SDK 抛出的 `TavilyError` 及所有子类
- HTTP 5xx / 429 由 Tavily SDK 内部转换为异常

**约束**: 重试仅作用于 Tavily API 调用本身；API key 校验失败不进入重试循环（在调用前直接返回降级结果）。

### 2.4 结果截断算法

```
输入: raw_text (网页摘要原文), max_chars (默认 4000)
逻辑:
  if len(raw_text) <= max_chars → 原样返回
  half = max_chars // 2
  return raw_text[:half] + "\n\n... [{原始长度} 字符截断] ...\n\n" + raw_text[-half:]
```

- `max_chars` 默认值取自 `settings.SEARCH_RESULT_MAX_LENGTH * 2`（即 10000）
- 每个结果的 `content` 字段独立截断，确保单条结果不爆炸
- 保留首尾：前半段包含标题/关键信息，后半段包含结论/URL

### 2.5 异常隔离分层

```
Layer 0: API Key 校验
  ├─ key 为空 / "your-*" / "test-*" → 返回降级 dict
  └─ 不抛异常，不进入重试

Layer 1: Tavily API 调用（含重试循环）
  ├─ for attempt in 0..max_retries:
  │    ├─ 成功 → break
  │    └─ 失败 → _classify_search_error(e) 分类 → 日志警告 → sleep → continue
  └─ 全部失败 → raise last_exc

Layer 2: 最外层异常捕获
  ├─ 捕获所有 Exception
  ├─ 日志 ERROR 级别记录：query / err_type / retries / elapsed_ms / exc
  └─ 返回降级 dict（status="failed", formatted="[搜索降级] ..."）

隔离保证:
  ├─ 任何异常不穿透到 AgentState
  ├─ 任何异常不中断 LangGraph 图执行
  └─ 降级提示是完整的自然语言句子，LLM 可直接基于它回答用户
```

### 2.6 日志埋点规范

**成功路径** (INFO):
```
[search_tool] Success | query=<截断100字符> | results=<条数> | retries=<次数> | elapsed=<毫秒>ms
```

**重试路径** (WARNING):
```
[search_tool] Retry <当前>/<上限> after <延迟>s | query=<截断> | err_type=<分类> | exc=<异常信息>
```

**失败路径** (ERROR):
```
[search_tool] Failed | query=<截断> | err_type=<分类> | retries=<次数> | elapsed=<毫秒>ms | exc=<完整异常>
```

**密钥未配置** (WARNING):
```
[search_tool] TAVILY_API_KEY not configured | query=<截断>
```

**异常类型分类** (`_classify_search_error`):
| 异常消息关键字 | 分类标签 |
|---------------|---------|
| `timeout` / `timed out` / `connect timeout` | `timeout` |
| `connection` / `network` / `refused` / `unreachable` | `network` |
| `rate` / `limit` / `429` / `too many` | `rate_limit` |
| `auth` / `key` / `unauthorized` / `401` / `403` | `auth` |
| 其他 | `unknown` |

---

## 3. ReAct 路由节点设计

### 3.1 路由判断 Prompt 设计

```
你是一个智能路由判断系统。根据用户输入和历史对话，判断下一步行动。

## 路由规则
1. **direct_reply**: 以下情况直接由 LLM 生成回复，不需要调用工具：
   - 闲聊、问候（如"你好""今天天气真好"）
   - 自我介绍类问题（如"你是谁""你能做什么"）
   - 纯主观意见/建议（如"你觉得怎么样""给我推荐"）
   - 已有工具结果需要整合回复时（由系统自动路由）

2. **tool_dispatch**: 以下情况必须调用工具获取外部信息：
   - 需要实时/时效性信息（如"今天天气""最新新闻""现在股价"）
   - 需要未知/不确定的外部知识（如"什么是XX""XX是什么意思"）
   - 需要搜索/查询具体事实（如"2024年奥运会金牌榜"）
   - 需要联网验证的信息

3. **end_conversation**: 用户明确表示结束对话时才使用。

## 输出格式
严格输出以下 JSON，不要添加任何其他内容：
{"action": "direct_reply|tool_dispatch|end_conversation", "reason": "不超过20字的判断理由", "selected_tools": []}

注意: selected_tools 仅在 action=tool_dispatch 时填写工具名列表（如 ["web_search"]），其他情况为空数组。
```

### 3.2 分支跳转逻辑

**router_node 处理流程**:

```
输入: AgentState
  │
  ├─ messages 为空 → next_action="end_conversation"
  ├─ tool_results 非空（有工具结果待回复）→ next_action="direct_reply"
  ├─ reflection_count >= MAX_REFLECTION_ROUNDS → next_action="direct_reply"
  │
  └─ 正常路由:
       ├─ 取最近 SHORT_TERM_MAX_MESSAGES 条消息
       ├─ 组装 [SystemMessage(ROUTER_PROMPT), ...recent, HumanMessage("请判断下一步行动")]
       ├─ ModelAdapter.invoke(state, messages)
       ├─ 解析 JSON → action, reason, selected_tools
       └─ JSON 解析失败 → 默认 action="direct_reply"
```

**should_continue 条件边映射**:

| next_action 值 | 条件边目标 | 说明 |
|---------------|-----------|------|
| `"end_conversation"` | `"end"` | 跳转 END |
| `"tool_dispatch"` | `"tools"` | 跳转 tool_dispatch 节点 |
| `"direct_reply"` | `"direct_reply"` | 跳转 direct_reply 节点（默认） |

### 3.3 AgentState 字段变更规则

**router_node 写入**:
| 字段 | 类型 | 写入规则 |
|------|------|----------|
| `next_action` | `str` | 路由判断结果: "direct_reply" / "tool_dispatch" / "end_conversation" |
| `selected_tools` | `list[str]` | 需调用的工具名列表，如 `["web_search"]` |
| `reflection_count` | `int` | 透传原值，不自增 |

**direct_reply_node 写入**:
| 字段 | 类型 | 写入规则 |
|------|------|----------|
| `messages` | `list[BaseMessage]` | 追加 LLM 生成的 AIMessage |
| `fallback_flag` | `bool` | 透传 ModelAdapter 返回的 fallback_flag |
| `tool_results` | `dict[str,str]` | 清空为 `{}`（结果已消费） |

**tool_dispatch_node 写入** (见第 6 节):
| 字段 | 类型 | 写入规则 |
|------|------|----------|
| `tool_calls` | `list[dict]` | 从 `selected_tools` 构造，含实际参数 |

**仅写入上述字段，不改动 AgentState TypedDict 定义本身（不新增/删除键）。**

---

## 4. ToolRegistry 注册标准 — SearchInput Schema

### 4.1 Pydantic 入参定义

```python
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    """搜索工具入参 Schema，适配 ToolRegistry 注册规范。"""
    query: str = Field(..., description="搜索查询词", min_length=1)
    max_results: int = Field(default=5, description="最大返回结果数", ge=1, le=10)
    search_depth: str = Field(default="advanced", description="搜索深度: basic 或 advanced")
```

### 4.2 ToolRegistry 注册参数

| 注册字段 | 值 |
|----------|-----|
| `name` | `"web_search"` |
| `description` | `"Tavily 联网搜索工具 — 搜索互联网获取实时信息、新闻、百科知识。适用场景：需要时效性信息、未知外部知识、事实查询。"` |
| `func` | `search_tool`（返回 `str` 的 ToolRegistry 兼容封装） |
| `parameters` | `SearchInput.model_json_schema()` 生成的 JSON Schema |

### 4.3 ToolRegistry 类型约束

- `ToolRegistry.ToolFunc = Callable[..., Coroutine[Any, Any, str]]`
- **必须**: 注册的函数返回 `str`，不能返回 `dict`
- **必须**: 注册的函数是 async（返回 coroutine）
- `_tool_execute_node` 通过 `asyncio.iscoroutine()` 自动检测 async/sync

### 4.4 注册时机

在 `get_agent()` 工厂函数内完成自动注册，确保生产路径和 CLI 路径均覆盖：

```
get_agent()
  ├─ 获取 ToolRegistry 单例
  ├─ 如果 "web_search" 未注册 → 注册 search_tool
  ├─ 获取 ModelAdapter 单例
  └─ 调用 build_agent_graph(...)
```

---

## 5. 单元测试覆盖场景清单

### 5.1 测试文件: `tests/test_tools/test_search_tool.py`

#### TestWebSearch — web_search 内核 (21 用例)

| # | 用例名 | 场景 | Mock 策略 |
|---|--------|------|-----------|
| 1 | `test_normal_query` | 正常搜索返回 success | mock `AsyncTavilyClient.search` 返回正常数据 |
| 2 | `test_empty_query` | 空查询仍正常返回 | mock 返回空 results |
| 3 | `test_timeout_retry` | 超时重试耗尽→failed | `side_effect = TimeoutError` |
| 4 | `test_network_disconnect` | 网络断开→优雅降级 | `side_effect = ConnectionRefusedError` |
| 5 | `test_rate_limit` | 限流 429→优雅降级 | `side_effect = Exception("429...")` |
| 6 | `test_missing_api_key_your_prefix` | key="your-..."→降级 | mock `get_settings` 返回占位符 key |
| 7 | `test_empty_api_key` | key=""→降级 | mock `get_settings` 返回空 key |
| 8 | `test_test_prefix_key` | key="test-..."→降级 | mock `get_settings` 返回 test 前缀 key |
| 9 | `test_truncation` | 超长文本截断 | 直接调用 `_truncate_result("A"*5000, 100)` |
| 10 | `test_no_truncation` | 短文本不截断 | 直接调用 `_truncate_result("Hello", 100)` |
| 11 | `test_max_results` | max_results 限制生效 | mock 返回 20 条, 请求 max_results=3 |
| 12 | `test_formatted_contains_query` | formatted 包含原查询 | 验证字符串包含 |
| 13 | `test_formatted_numbered` | formatted 有序号 | 验证 "1." "2." |
| 14 | `test_has_status_field` | 返回结构完整 | 验证 status/query/results/formatted/retry_count/elapsed_ms |
| 15 | `test_search_depth` | depth 参数传递 | 验证 `call_args.kwargs["search_depth"]` |
| 16 | `test_retry_then_success` | 首次失败后重试成功 | `side_effect = [TimeoutError, 正常数据]` |
| 17 | `test_snippet_fallback` | content 为空回退 snippet | mock 返回 content="" |
| 18 | `test_special_chars` | 特殊字符查询 | query="test + query #1" |
| 19 | `test_formatted_has_url` | 结果含 URL | 验证 URL 在 formatted 中 |
| 20 | `test_default_max_results` | 默认 ≤5 条 | 不传 max_results, mock 返回 10 条 |
| 21 | `test_elapsed_ms_field` | elapsed_ms 为 ≥0 int | 类型和值校验 |
| 22 | `test_retry_count_on_success` | 首次成功 retry_count=0 | 常规断言 |

#### TestSearchTool — search_tool 封装 (3 用例)

| # | 用例名 | 场景 |
|---|--------|------|
| 1 | `test_returns_string` | 返回 str 类型（非 dict） |
| 2 | `test_returns_degraded_on_failure` | 搜索失败返回降级字符串，不抛异常 |
| 3 | `test_passes_max_results` | max_results 参数正确穿透 |

#### TestSearchInput — Pydantic Schema (5 用例)

| # | 用例名 | 场景 |
|---|--------|------|
| 1 | `test_valid_input` | 合法参数构造 |
| 2 | `test_default_values` | 默认值验证 (max_results=5, depth=advanced) |
| 3 | `test_empty_query_rejected` | query="" 被 pydantic 拒绝 (min_length=1) |
| 4 | `test_max_results_cap` | max_results=10 通过 |
| 5 | `test_max_results_exceeded_rejected` | max_results=11 被拒绝 (le=10) |

#### TestClassifySearchError — 异常分类 (7 用例)

覆盖 timeout / network / rate_limit / auth(2) / unknown 六种分类结果。

#### TestRetryWithBackoff — 遗留重试函数 (3 用例)

保持与 v0.2.1 一致，覆盖首次成功、重试后成功、全部失败。

### 5.2 Mock 异常模拟方案

```
核心策略: patch("tools.search_tool.AsyncTavilyClient")
  │
  ├─ 正常场景: mock_instance.search.return_value = {"results": [...]}
  ├─ 超时: mock_instance.search.side_effect = TimeoutError("timeout")
  ├─ 网络断开: mock_instance.search.side_effect = ConnectionRefusedError("Connection refused")
  ├─ 限流: mock_instance.search.side_effect = Exception("429 Too Many Requests")
  ├─ 认证失败: mock_instance.search.side_effect = Exception("401 Unauthorized")
  └─ 重试后成功: mock_instance.search.side_effect = [TimeoutError, {"results": [...]}]

密钥校验旁路: patch("tools.search_tool.get_settings")
  └─ mock_settings.TAVILY_API_KEY = "your-..." / "" / "test-..."
```

---

## 6. agent_graph 图节点改造

### 6.1 现状问题

**Bug A — `_tool_dispatch_node` 空参数传递**:
当前实现将 `selected_tools` 直接转为 `tool_calls` 且 `params` 恒为 `{}`:
```python
tcs = [{"tool": t, "params": {}, "status": "pending"} for t in state.get("selected_tools", [])]
```
这导致 `_tool_execute_node` 调用 `search_tool(**{})` 时缺少必填参数 `query`，工具执行失败。

**Bug B — `_tool_execute_node` 对 dict 返回值处理不兼容**:
当前代码对 async 结果直接赋值 `tool_output: str = await maybe_coro`。若被注册的工具返回 `dict`（如 `web_search`），`tool_results` 中会存入 dict 而非 str，导致下游 `_result_integration_node` 中 `"错误" in v` 检查 dict key 而非 value。

### 6.2 改造方案

#### 6.2.1 `_tool_dispatch_node` — 参数提取逻辑

```
改造后流程:
  │
  ├─ 遍历 state["selected_tools"]
  │    ├─ 工具名 == "web_search":
  │    │    └─ params = {"query": <最后一条用户消息的 content>}
  │    └─ 其他工具:
  │         └─ params = {}  (保持向后兼容)
  │
  └─ 构造 tool_calls: {"tool": t, "params": params, "status": "pending"}
```

**query 提取规则**:
- 从 `state["messages"]` 倒序遍历
- 取第一个 `content` 不为空的消息的 `content` 字符串
- 不做语义加工，原样传递

#### 6.2.2 `_tool_execute_node` — 防御式结果处理

```
改造后流程:
  │
  ├─ func(**params) → maybe_coro
  │
  ├─ 异步路径 (iscoroutine):
  │    ├─ raw = await maybe_coro
  │    ├─ isinstance(raw, dict) → tool_output = raw.get("formatted", str(raw))
  │    └─ else → tool_output = str(raw)
  │
  └─ 同步路径:
       ├─ isinstance(maybe_coro, dict) → tool_output = maybe_coro.get("formatted", str(maybe_coro))
       └─ else → tool_output = str(maybe_coro)
```

**约束**: 不修改 `ToolRegistry` 签名规范，仅在图节点层面做防御。

#### 6.2.3 `_result_integration_node` — 值检查兼容

```
改造后:
  errors = []
  for k, v in tr.items():
      if isinstance(v, str):
          if "错误" in v or "未注册" in v:
              errors.append(k)
      elif isinstance(v, dict):
          # 防御：dict 类型结果视为无错误（业务降级已在工具层处理）
          pass
```

**设计决策**: dict 类型结果不触发 reflection。原因：
- 搜索工具的降级返回 `{"status": "failed", "formatted": "[搜索降级]..."}` 已在工具层闭环
- 触发 reflection 会导致不必要的重试，违背故障隔离原则
- reflection 仅用于工具执行层的硬错误（未注册、代码异常）

#### 6.2.4 `get_agent()` — 自动注册

```
改造后:
  def get_agent():
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
                  description="Tavily 联网搜索工具...",
                  func=search_tool,
                  parameters=SearchInput.model_json_schema(),
              )

          _compiled_agent = build_agent_graph(get_model_adapter(), reg)
      return _compiled_agent
```

### 6.3 图结构不变部分

以下节点/边**不做任何修改**:
- `preprocess` → END 的条件边
- `preprocess` → router 的条件边
- `direct_reply` → memory_update 的固定边
- `tool_dispatch` → tool_execute → result_integration 的固定边
- `result_integration` → router (reflection) / memory_update 的条件边
- `memory_update` → END 的固定边
- 所有 7 节点的 `add_node` 调用
- `MemorySaver` checkpointer

---

## 7. 门禁校验约束 & 覆盖率保障方案

### 7.1 门禁执行命令

```bash
# 1. Ruff 格式化检查（不自动修改）
python -m ruff format --check .

# 2. Ruff Lint（零报错，使用 pyproject.toml 已有规则）
python -m ruff check .

# 3. Mypy 严格模式（仅检查源码，排除 tests/）
python -m mypy --strict .

# 4. Pytest 全量用例 + 覆盖率报告
python -m pytest tests/ -v --cov=. --cov-report=term --cov-report=html --cov-fail-under=90

# 5. 针对性新增测试先行验证
python -m pytest tests/test_tools/test_search_tool.py -v --cov=tools.search_tool --cov-report=term
```

### 7.2 门禁标准

| 检查项 | 标准 | 适用范围 |
|--------|------|----------|
| ruff format | 零差异 | 全项目 |
| ruff check | 零报错 | 全项目 |
| mypy --strict | 零报错 | `*.py` 排除 `tests/` |
| pytest | 全量通过，0 失败 | `tests/` |
| coverage | ≥ 90% | 全项目 |
| 新增代码覆盖率 | 100% | `tools/search_tool.py` (新增部分) |

### 7.3 覆盖率保障方案

**新增代码逐函数对照**:

| 函数 | 测试覆盖 | 覆盖路径 |
|------|---------|----------|
| `SearchInput` | `TestSearchInput` (5 用例) | 合法/默认/边界拒绝(空/min/max) |
| `_truncate_result` | 2 用例 | 截断分支 + 不截断分支 |
| `_classify_search_error` | `TestClassifySearchError` (7 用例) | 5 种分类 + unknown |
| `web_search` | `TestWebSearch` (22 用例) | 成功/空查询/超时/网络/限流/密钥(3种)/截断/max_results/formatted(4)/depth/重试成功/snippet回退/特殊字符/elapsed/retry_count |
| `search_tool` | `TestSearchTool` (3 用例) | 返回str/失败降级/参数穿透 |
| `_retry_with_backoff` | `TestRetryWithBackoff` (3 用例) | 首次成功/重试成功/全部失败 |

**不可覆盖的防御代码**:
- `assert last_exc is not None` (line 115-116 in search_tool.py): 逻辑上不可达（for-else 仅在循环未 break 时触发，此时 `last_exc` 必然被赋值）。在 `pyproject.toml` 的 `[tool.coverage.report]` 中添加 `exclude_also` 注释标记 `# pragma: no cover` 排除。

---

## 8. 开发分步执行流程

```
Step 1: tools/search_tool.py
  ├─ 实现 SearchInput(BaseModel)
  ├─ 实现 _classify_search_error()
  ├─ 重写 web_search() — 结构化日志 + retry_count/elapsed_ms 字段
  ├─ 新增 search_tool() — ToolRegistry 兼容封装 (→ str)
  ├─ 保留 _retry_with_backoff / _truncate_result
  ├─ 更新 __all__
  └─ 验证: python -c "from tools.search_tool import search_tool, web_search, SearchInput" ✓

Step 2: 单元测试
  ├─ 编写 tests/test_tools/test_search_tool.py (35 用例)
  ├─ python -m pytest tests/test_tools/test_search_tool.py -v → 全部 PASS
  ├─ python -m pytest tests/test_tools/test_search_tool.py --cov=tools.search_tool --cov-report=term
  │    └─ 新增代码覆盖率 100%
  └─ 验证: 无任何外部依赖（全部 mock）

Step 3: core/router_node.py
  ├─ 增强 ROUTER_PROMPT — 明确区分闲聊/搜索场景
  ├─ router_node / direct_reply_node / should_continue 逻辑不变
  └─ 验证: python -m pytest tests/test_core/test_router_node.py -v → 全部 PASS

Step 4: ToolRegistry 自动注册
  ├─ 修改 core/agent_graph.py get_agent()
  ├─ 添加幂等注册逻辑（if "web_search" not in reg.list_tools()）
  └─ 验证: 两次调用 get_agent() 不重复注册

Step 5: agent_graph.py 图结构改造
  ├─ 改造 _tool_dispatch_node — 提取 query 参数
  ├─ 改造 _tool_execute_node — 防御 dict 返回值
  ├─ 改造 _result_integration_node — 防御 dict 值检查
  └─ 验证: python -m pytest tests/test_core/test_agent_graph.py -v → 全部 PASS

Step 6: 全量门禁
  ├─ python -m ruff format --check .  → 零差异
  ├─ python -m ruff check .            → 零报错
  ├─ python -m mypy --strict .         → 零报错
  ├─ python -m pytest tests/ -v --cov=. --cov-fail-under=90  → 全部 PASS
  └─ 验证: 整体覆盖率 ≥ 90%, 新增代码覆盖率 100%
```

---

## 附录 A: 关键设计决策与边界约束

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 双函数模式 (web_search + search_tool) | 保留两个函数 | `web_search` 返回 dict 供程序化使用，`search_tool` 返回 str 符合 ToolRegistry 规范 |
| 异常处理层级 | 工具内部全量捕获 | 故障隔离原则：任何异常不穿透到 AgentState、不中断图执行 |
| reflection 触发条件 | 仅硬错误触发 | dict 类型的业务降级结果不触发 reflection（已在工具层闭环） |
| query 参数来源 | 最后一条用户消息 content | 最小改动原则，不修改 router_node 输出结构 |
| 注册时机 | `get_agent()` 懒加载 | 覆盖 CLI 和 API 两条路径 |
| AgentState 字段 | 不新增/不删除 | 向后兼容 v0.2.1 归档版本 |

## 附录 B: 不改动的文件清单

以下文件本次迭代**完全不触碰**:
- `core/agent_state.py` — TypedDict 定义不变
- `core/model_adapter.py` — 模型适配逻辑不变
- `core/tool_registry.py` — 注册中心 API 不变
- `core/exceptions.py` — 异常类定义不变
- `core/logger.py` — 日志系统不变
- `config/settings.py` — 配置项不变（SEARCH_* 已就绪）
- `config/constants.py` — 常量委托不变
- `config/error_codes.py` — 错误码不变
- `memory/` — 三层记忆系统不变
- `storage/` — 持久化存储不变
- `api/` / `frontend/` — 接口/前端不变
- `tests/` 中除 `test_tools/test_search_tool.py` 外的全部文件

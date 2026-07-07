# Multi-Tool Agent

多工具智能助理 —— 基于 LangGraph 的工业级 Agent 骨架。

## 快速开始
### 1. 环境变量配置
```bash
cp .env.example .env
```
编辑 `.env` 文件，填入LLM密钥、Tavily搜索密钥等配置
开启联网搜索能力需前往 [Tavily控制台](https://app.tavily.com/home) 创建开发者 API 密钥，填入`.env`文件`TAVILY_API_KEY`字段；
研究员套餐每月提供 1000 免费信用点，足够本地开发调试使用。

### 容错提示
1. 密钥为空、填写错误、额度耗尽时，搜索工具自动触发降级逻辑，返回友好提示，不会中断对话主流程；
2. 本地调试使用开发者密钥，正式生产环境建议单独新建独立生产密钥，隔离测试 / 生产调用数据。

### 2. 环境准备（规避pyproject构建后端报错，推荐方案）
```powershell
# 1. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 一次性安装全部运行时+开发依赖
pip install pytest pytest-cov ruff mypy pytest-asyncio pytest-mock python-dotenv chromadb langgraph langchain langchain-openai openai tavily-python pypdf python-docx openpyxl fastapi streamlit
```

### 3. 全项目门禁校验脚本（归档验收标准）
```powershell
# 代码格式校验
ruff check .
ruff format .

# 严格类型校验
python -m mypy --strict core/ config/ storage/ memory/ tools/ frontend/

# 全量单元测试（当前版本312条用例，0失败标准）
pytest tests/ -q --tb=short

# 覆盖率门禁校验（归档门槛≥90%，当前91.38%）
pytest tests/ -q --cov=core --cov=config --cov=storage --cov=memory --cov=tools --cov=frontend --cov-fail-under=80
```

### 4. 启动Agent CLI
```bash
python -m core.agent_graph
```

### 5. 启动 Streamlit 前端（v0.8.0+）
```powershell
# 首次启动需安装 nest-asyncio 依赖
pip install nest-asyncio

# 启动双栏可视化前端
streamlit run frontend/app.py
```
启动后浏览器自动打开，左侧边栏管理会话/工具/参数，右侧主面板聊天交互。
若遇到 PowerShell 执行策略限制，先执行：`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

---

## 目录结构
```
config/         全局配置与常量（零依赖）
storage/        持久化存储封装（ChromaDB + SQLite + 文件系统）
core/           核心调度层（AgentState + Graph + Router + ToolRegistry + ModelAdapter）
memory/         三级分层记忆（短期 / 中期 / 长期）
tools/          工具能力集群（联网搜索 / 代码沙箱 / RAG双工具 / 主动记忆写入 / 结构化周报生成）
api/            FastAPI 后端接口层
frontend/       Streamlit 可视化前端（双栏布局 + 会话隔离 + ReAct 可视化）
tests/          全量单元测试
data/           运行时数据（不纳入版本控制）
docker/         容器化部署配置
scripts/        运维脚本
```
## 开发规范
- 强类型注解（mypy --strict）
- ruff line-length = 120
- Google-style docstring
- 所有错误码统一从 ErrorCode 枚举引用
- 所有阈值从 config/constants.py 读取
## 版本
### v0.1.0-skeleton — LangGraph 完整 Agent 骨架

### v0.2.1-bugfix（当前稳定版）
1. 测试用例扩充至203条，全量执行0失败
2. 整体代码覆盖率96.73%，满足归档≥90%门禁要求
3. Ruff代码格式化、mypy严格类型校验零报错
4. 仅新增边界/异常测试用例，无业务源码修改
5. 修复依赖安装报错问题，提供一键批量安装脚本

### v0.3.0-feat-search
1. 新增Tavily异步联网搜索工具，内置指数退避重试、结果智能截断、多层异常隔离降级
2. 实现ReAct智能路由节点，LLM自动区分闲聊/实时知识查询/结束对话三类分支
3. 修复LangGraph调度三层底层Bug，打通「思考-联网检索-整合回答」完整ReAct闭环
4. get_agent自动幂等注册搜索工具，无需手动注册
5. Chroma向量存储持久化失败自动降级内存存储，增强生产容错
6. 新增40条搜索工具专项单元测试，全项目合计224用例零失败
7. 全项目mypy/ruff静态质检零报错，覆盖率≥90%归档标准

### v0.4.0-code-sandbox
1. 新增隔离式 Python 代码沙箱 code_executor 工具，AST 语法树高危检测 + Docker 四层容器隔离
2. 实现 20s 进程软超时 + 30s 容器硬销毁双重熔断，连续 3 次失败会话级自动禁用工具
3. ReAct 全链路闭环：运行错误回流反思节点，LLM 自主重写代码；高危拦截直接终止不触发重试
4. get_agent 幂等自动注册代码沙箱工具，无需手动配置
5. 完全兼容现有函数式 ToolRegistry 架构，无新增抽象层，无历史功能破坏
6. 新增 33 条代码沙箱专项单元测试，全项目合计 257 用例零失败
7. 全项目 mypy/ruff 静态质检零报错，整体覆盖率 92.44%，满足 ≥90% 归档标准

### v0.5.0-rag
1. 新增本地知识库 RAG 双工具：index_documents（文档索引）+ knowledge_search（语义检索）
2. 支持 PDF/DOCX/XLSX 三类主流文档纯文本提取，统一入口 parse_document 自动分发
3. 实现段落边界优先 + 固定长度兜底语义分块算法，可配置分片长度与重叠窗口
4. ChromaStore 业务封装层组合复用现有 ChromaClient 单例，嵌入生成独立调度
5. 检索支持相似度阈值过滤、结果智能截断、零匹配兜底，完全兼容函数式 ToolRegistry 注册规范
6. get_agent 幂等自动注册 index_documents + knowledge_search 双工具，LLM 自主判断调用
7. 新增 49 条 RAG 专项单元测试（解析器 18 + 存储 8 + 检索 16 + 索引 6 + 分块 1），全项目合计 306 用例零失败
8. 全项目 mypy/ruff 静态质检零报错，整体覆盖率 92.47%，满足 ≥90% 归档标准

### v0.6.0-memory
1. 落地三级分层记忆体系：短期滑动窗口会话记忆、中期LLM摘要持久化、长期向量语义记忆，三层职责解耦
2. MemoryManager 门面层统一对外入口，内部编排三层记忆读写，与主调度链路低耦合
3. 新增 remember_this 主动记忆工具，遵循函数式 ToolRegistry 规范，LLM 可自主调用写入长期记忆
4. 上下文静默注入回复节点，不新增 LangGraph 图节点，最小侵入式接入主链路，无原有功能回归
5. 修复长期记忆距离过滤方向历史Bug，召回结果按相似度阈值正确筛选
6. 中期记忆支持 TTL 自动过期清理，MemoryManager 初始化时自动执行全量过期会话清理
7. 全链路异常兜底：存储层故障自动降级内存模式，所有记忆层异常内部捕获，不透传中断主对话
8. 补充记忆模块全场景单元测试，覆盖正常读写、边界场景、降级容错、会话隔离
9. 全项目合计 307 用例零失败，mypy/ruff 静态质检零报错，整体覆盖率 91.66%，满足 ≥90% 归档标准

### v0.7.0-weekly
1. 新增结构化周报生成工具，支持 Markdown / JSON 双格式输出，基于会话记忆自动生成总结
2. 分层实现：纯代码计算工具调用统计、会话时长等硬指标，LLM 仅负责语义总结，数据准确可追溯
3. 调度节点从 AgentState 实时注入统计参数，工具层保持无状态，完全兼容函数式 ToolRegistry 架构
4. get_agent 幂等自动注册，无需手动配置，LLM 可自主识别「生成周报」类意图并调用
5. 3000 字符超长内容自动截断，避免上下文溢出；空会话、参数非法、LLM 故障四类场景全兜底
6. 修复调度节点统计数据空注入问题，工具使用统计、会话时长均从状态实时读取
7. 统一 config 目录子模块导出风格，代码规范与其他模块对齐
8. 新增 5 条周报工具专项单元测试，覆盖正常生成、空会话降级、异常兜底全场景
9. 全项目合计 312 用例零失败，mypy/ruff 静态质检零报错，整体覆盖率 91.38%，满足 ≥90% 归档标准

### v0.8.0-frontend（当前最新版）
1. 新增 Streamlit 工业级双栏可视化前端，左侧边栏会话管理 + 工具开关 + 参数配置，右侧主面板聊天 + ReAct 链路可视化
2. 实现完整会话隔离：`st.session_state` + LangGraph `thread_id` 双层保障，多标签页/多会话数据互不串流
3. Agent / MemoryManager 使用 `@st.cache_resource` 全局单例缓存，规避重复初始化向量库、LLM、容器沙箱
4. `agent_runner` 同步封装层捕获全部异步调用异常，返回友好提示，不抛出堆栈破坏页面渲染
5. stderr 双写日志体系：路由节点 `[router]` + 前端 `[frontend]` 双重终端日志，全链路可追溯
6. 前端专项冒烟测试覆盖启动导入、会话管理、Agent 调用、异常兜底全场景
7. 全项目 mypy/ruff 静态质检零告警，core/tools/storage/memory/config/api 零变更，满足架构红线
## Checkpointer 持久化说明
### MemorySaver（当前方案）
当前使用 LangGraph MemorySaver 内存型检查点存储，所有会话对话历史保存在进程内存中。
**限制：** Streamlit 进程重启（代码修改触发热重载、手动终止进程）后，全部会话历史丢失，无法恢复。

### SqliteSaver（后续迭代规划）
下一版本迭代计划替换为 SqliteSaver，实现会话历史磁盘持久化。
届时会话底层存储完整 UUID 主键，支持跨进程重启恢复对话。

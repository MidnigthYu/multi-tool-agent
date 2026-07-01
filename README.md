# Multi-Tool Agent

多工具智能助理 —— 基于 LangGraph 的工业级 Agent 骨架。

## 快速开始
### 1. 环境变量配置
```bash
cp .env.example .env
```
编辑 `.env` 文件，填入LLM密钥、Tavily搜索密钥等配置

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
mypy --strict core/ config/ storage/ memory/ tools/

# 全量单元测试（当前版本203条用例，0失败标准）
pytest tests/ -q --tb=short

# 覆盖率门禁校验（归档门槛≥90%，当前96.73%）
pytest tests/ -q --cov=core --cov=config --cov=storage --cov=memory --cov=tools --cov-fail-under=90
```

### 4. 启动Agent CLI
```bash
python -m core.agent_graph
```

---

## 目录结构
```
config/         全局配置与常量（零依赖）
storage/        持久化存储封装（ChromaDB + SQLite + 文件系统）
core/           核心调度层（AgentState + Graph + Router + ToolRegistry + ModelAdapter）
memory/         三级分层记忆（短期 / 中期 / 长期）
tools/          工具能力集群（搜索 / 文档解析 / 代码助手 / 周报生成）
api/            FastAPI 后端接口层
frontend/       Streamlit 可视化前端
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
v0.1.0-skeleton — LangGraph 完整 Agent 骨架

### v0.2.1-bugfix（当前稳定版）
1. 测试用例扩充至203条，全量执行0失败
2. 整体代码覆盖率96.73%，满足归档≥90%门禁要求
3. Ruff代码格式化、mypy严格类型校验零报错
4. 仅新增边界/异常测试用例，无业务源码修改
5. 修复依赖安装报错问题，提供一键批量安装脚本
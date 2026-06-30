# Multi-Tool Agent

多工具智能助理 —— 基于 LangGraph 的工业级 Agent 骨架。

## 快速开始
```bash
# 1. 复制环境变量模板并填写
cp .env.example .env
# 2. 安装依赖
pip install -e .
pip install -e ".[dev]"
# 3. 运行 CLI
python -m core.agent_graph
```
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

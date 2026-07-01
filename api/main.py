"""FastAPI 应用入口 -- 骨架阶段提供 /health 端点。"""

from __future__ import annotations

from fastapi import FastAPI

app: FastAPI = FastAPI(title="多工具智能助理", version="0.1.0")


@app.get("/health")  # type: ignore[untyped-decorator]
async def health() -> dict[str, str]:
    return {"status": "ok"}

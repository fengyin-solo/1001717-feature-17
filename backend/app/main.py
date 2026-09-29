"""特种设备点检运维平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.services.contract import STATUS_REFRESHERS, ContractService
from app.store import store

contract_service = ContractService()

app = FastAPI(title="特种设备点检运维平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：合同履约状态先按统一口径重算，在履合同数随之刷新。"""
    data = store.overview(status_refresh=STATUS_REFRESHERS)
    cards = list(data["cards"])
    cards.append({"label": "在履合同数", "value": contract_service.count_active()})
    data["cards"] = cards
    return data

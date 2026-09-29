"""维保合同接口：按服务单位归属控制可见范围，覆盖登记、状态流转、金额/到期调整、
归属变更、删除引用拦截与履约历史查询。共用服务单位信息只读。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contract import ContractService

router = APIRouter(prefix="/api/contract", tags=["维保合同"])

service = ContractService()

# 列表列：合同状态口径不统一，改用后端统一判定的「履约状态」
LIST_FIELDS = ["合同编号", "服务单位", "维保设备", "合同金额", "服务期限", "签订人员", "到期日期", "履约状态"]
STATUSES = ["待签订", "履行中", "已到期", "已终止"]
SCOPES = ["mine", "shared", "missing"]


@router.get("/units")
def list_units() -> dict[str, Any]:
    """服务单位名录：集团共用单位标记 shared=true，名录信息只读，不提供修改入口。"""
    return {"items": service.list_units()}


@router.get("", response_model=PageResult[dict])
def list_entries(
    unit: str | None = Query(default=None, description="当前服务单位（归属口径）"),
    scope: str = Query(default="mine", description="mine=本单位 / shared=共用只读 / missing=归属缺失"),
    keyword: str | None = Query(default=None, description="按合同编号检索"),
    status: str | None = Query(default=None, description="待签订、履行中、已到期、已终止"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按归属范围列出合同：本单位可维护、共用单位只读、归属缺失单独列出。"""
    if scope not in SCOPES:
        scope = "mine"
    if size > 200:
        return PageResult(items=[], total=0, page=page, size=size)
    items, total, summary = service.list_entries(
        unit=unit, scope=scope, keyword=keyword, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size, summary=summary)


@router.get("/export")
def export_entries(
    unit: str | None = Query(default=None),
    scope: str = "mine",
) -> dict[str, Any]:
    """导出合同清单：与列表同一套归属范围和履约口径。"""
    if scope not in SCOPES:
        scope = "mine"
    items, total, _ = service.list_entries(unit=unit, scope=scope, page=1, size=10000)
    return {"module": "contract", "unit": unit, "scope": scope, "total": total, "items": items}


@router.get("/{entry_id}", response_model=ActionResult)
def get_entry(entry_id: int, unit: str | None = Query(default=None)) -> ActionResult:
    """读取单条合同明细；跨单位访问会被拦下并说明原因。"""
    entry, message = service.get_entry(entry_id, unit=unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="ok", entry=entry)


@router.get("/{entry_id}/history")
def get_history(entry_id: int, unit: str | None = Query(default=None)) -> dict[str, Any]:
    """履约历史：归属变更后旧记录仍挂在原服务单位名下。"""
    rows, message = service.get_history(entry_id, unit=unit)
    if message and not rows:
        return {"ok": False, "message": message, "items": []}
    return {"ok": True, "message": "ok", "items": rows}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, unit: str | None = Query(default=None)) -> ActionResult:
    """登记合同：归属强制取当前服务单位；共用单位与跨单位登记直接拦下。"""
    entry, message = service.create_entry(payload.values, unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="维保合同已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload, unit: str | None = Query(default=None)) -> ActionResult:
    """确认签订、标记到期、终止合同；非本单位合同与共用单位合同只读，操作会被拦下。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def adjust_entry(entry_id: int, payload: EntryPayload, unit: str | None = Query(default=None)) -> ActionResult:
    """调整合同金额或到期日期，调整后履约状态按归属重新判定。"""
    entry, message = service.adjust_entry(entry_id, payload.values, unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}/owner", response_model=ActionResult)
def change_owner(entry_id: int, payload: EntryPayload, unit: str | None = Query(default=None)) -> ActionResult:
    """变更/认领归属：跨单位改动需原归属单位发起；历史履约记录留在原服务单位名下。"""
    target = payload.values.get("服务单位")
    entry, message = service.change_owner(entry_id, target, unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.delete("/{entry_id}", response_model=ActionResult)
def delete_entry(entry_id: int, unit: str | None = Query(default=None)) -> ActionResult:
    """删除合同；已被别家单位引用时拦下并说明引用方。"""
    ok, message = service.delete_entry(entry_id, unit)
    return ActionResult(ok=ok, message=message)

"""维保合同接口：按服务单位划分归属，覆盖登记、编辑、状态流转、归属变更、认领与删除。

可见范围随请求头 X-Service-Unit 切换：本单位合同可维护，共用服务单位只读，
归属缺失单独列出；跨单位改动一律 403 并在 detail 里说明原因。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import settings
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contract import MODULE, ContractService, ScopeError

router = APIRouter(prefix="/api/contract", tags=["维保合同"])

service = ContractService()

LIST_FIELDS = ["合同编号", "服务单位", "维保设备", "合同金额", "服务期限", "签订人员", "到期日期"]
STATUSES = ["待签订", "履行中", "已到期", "已终止"]
SCOPES = ["mine", "shared", "missing", "legacy", "all_visible"]


def _guard(func, *args, **kwargs):
    """统一把跨单位拦截转成 403，消息即拦截原因；不存在转 404。"""
    try:
        return func(*args, **kwargs)
    except ScopeError as exc:
        if not str(exc):
            raise HTTPException(status_code=404, detail="维保合同不存在或已归档")
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/units")
def list_units() -> dict[str, Any]:
    """返回当前可切换的服务单位、默认单位与共用单位，供前端切换归属视角。"""
    return service.list_units()


@router.get("/summary")
def summary(
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> dict[str, int]:
    """合同看板指标：在履合同数等与列表、详情、运营概览取同一份状态口径。"""
    return service.summary(unit=x_service_unit)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按合同编号检索"),
    status: str | None = Query(default=None, description="待签订、履行中、已到期、已终止"),
    scope: str = Query(default="mine", description="mine 本单位 / shared 共用只读 / missing 归属缺失 / legacy 已转出留档 / all_visible"),
    page: int = 1,
    size: int = 20,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> PageResult[dict]:
    """按归属范围、合同编号与状态过滤；他单位合同不会出现在任何可见范围里。"""
    if size > settings.page_size_max:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail=f"归属范围「{scope}」不合法，可选：{'、'.join(SCOPES)}")
    items, total = service.list_entries(
        unit=x_service_unit, scope=scope, keyword=keyword, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    scope: str = "all_visible",
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> dict[str, Any]:
    """导出当前单位可见范围内的合同清单；他单位合同不在导出结果中。"""
    if scope not in SCOPES:
        scope = "all_visible"
    items, total = service.list_entries(unit=x_service_unit, scope=scope, page=1, size=10000)
    return {"module": MODULE, "scope": scope, "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> dict:
    """读取单条合同明细及履约记录；他单位合同返回 403，不存在返回 404。"""
    entry = _guard(service.get_entry, entry_id, unit=x_service_unit)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"维保合同 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """登记合同，新合同自动归属当前单位；缺字段或挂到他单位名下会被拦下并说明原因。"""
    try:
        entry, missing = service.create_entry(payload.values, unit=x_service_unit)
    except ScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="维保合同已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(
    entry_id: int,
    payload: EntryPayload,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """修改金额、到期日期等字段；共用只读、跨单位修改一律拦下，改完履约状态重新判定。"""
    entry, message = _guard(service.update_entry, entry_id, payload.values, unit=x_service_unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """对单条合同执行确认签订、标记到期、终止合同；不允许或跨单位的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = _guard(service.run_action, entry_id, action, unit=x_service_unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/transfer", response_model=ActionResult)
def transfer_ownership(
    entry_id: int,
    payload: EntryPayload,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """归属变更：仅归属单位可发起；变更后历史履约记录仍保留在原服务单位名下。"""
    target = str(payload.values.get("目标单位") or "").strip()
    entry, message = _guard(service.transfer_ownership, entry_id, target, unit=x_service_unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/claim", response_model=ActionResult)
def claim_ownership(
    entry_id: int,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """认领归属缺失的合同：补录到当前单位名下后才可维护。"""
    entry, message = _guard(service.claim_ownership, entry_id, unit=x_service_unit)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.delete("/{entry_id}", response_model=ActionResult)
def delete_entry(
    entry_id: int,
    x_service_unit: str | None = Header(default=None, alias="X-Service-Unit"),
) -> ActionResult:
    """删除合同：他单位/共用合同拦下，已被结算单（履约记录）引用的合同不能直接删除。"""
    ok, message = _guard(service.delete_entry, entry_id, unit=x_service_unit)
    return ActionResult(ok=ok, message=message)

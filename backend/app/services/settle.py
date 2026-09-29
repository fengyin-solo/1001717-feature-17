"""费用结算业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.store import store

MODULE = "settle"
REQUIRED_FIELDS = ["结算单号", "关联合同", "费用类别"]
STATUS_ORDER = ["待核算", "待审核", "已付款", "已驳回"]
ACTION_RULES = {"提交审核": "待审核", "确认付款": "已付款", "驳回结算": "已驳回"}
NEGATIVE_ACTIONS = ["驳回结算"]


class SettleService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("结算单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(
        self, values: dict[str, Any], *, unit: str | None = None
    ) -> tuple[dict[str, Any] | None, list[str], str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        viewer = settings.unit_name(str(unit or "").strip()) if str(unit or "").strip() else ""
        # 结算单是合同的履约记录：只能由合同归属单位发起，共用/他单位/归属缺失都拦下。
        contract_code = str(values.get("关联合同") or "").strip()
        contract = next(
            (row for row in store.rows("contract") if str(row.get("合同编号") or "").strip() == contract_code),
            None,
        )
        if contract is None:
            return None, [], f"关联合同「{contract_code}」不存在，不能登记履约结算"
        owner = str(contract.get("服务单位") or "").strip()
        if not owner:
            return None, [], f"合同「{contract_code}」归属缺失，需先认领补录归属后再办理结算"
        if owner == settings.shared_name:
            return None, [], f"合同「{contract_code}」属共用档案，不产生具体单位的履约结算"
        if viewer and owner != viewer:
            return None, [], (
                f"合同「{contract_code}」归属「{owner}」，{viewer}不能跨单位登记其履约结算"
            )
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 快照履约单位：合同日后归属变更，这条历史记录仍留在原单位名下。
        entry["履约单位"] = owner
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, [], ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"结算单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于费用结算可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"结算单已{action}"

"""维保合同业务规则。

归属与履约可见范围的口径统一收在这里：
- 合同按「服务单位」划分归属，当前服务单位只能查看和维护本单位的合同；
- 集团共用服务单位的合同（以及服务单位名录本身）只读，任何单位都不能改动；
- 跨单位的改动一律拦下，并返回可读的原因；
- 履约状态只由 refresh_status 一处按合同金额与到期日期判定，列表、详情、概览共用；
- 归属变更不搬迁历史：履约历史按发生时的归属单位留痕，永远留在原服务单位名下；
- 已被别家单位引用的合同不能直接删除。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from app.store import store

MODULE = "contract"
HISTORY_MODULE = "contract_history"
SETTLE_MODULE = "settle"

REQUIRED_FIELDS = ["合同编号", "服务单位", "维保设备"]
EDITABLE_FIELDS = ["合同金额", "到期日期"]
STATUS_ORDER = ["待签订", "履行中", "已到期", "已终止"]
STATUS_SIGNED = "履行中"
STATUS_EXPIRED = "已到期"
STATUS_TERMINATED = "已终止"
STATUS_UNSIGNED = "待签订"
ACTION_RULES = {"确认签订": "signed", "标记到期": "forced_expired", "终止合同": "terminated"}

OWNER_FIELD = "服务单位"
UNIT_FIELD = "归属单位"   # 履约历史里留痕用的快照字段
REF_OWNER_FIELD = "归属单位"  # 结算单引用合同时记录的归属单位

# 服务单位名录：集团共用的服务单位信息全平台只读
SERVICE_UNITS = [
    {"name": "华东维保站", "shared": False},
    {"name": "华北维保站", "shared": False},
    {"name": "华南维保站", "shared": False},
    {"name": "西南维保站", "shared": False},
    {"name": "园区维保点", "shared": False},
    {"name": "集团共用维保中心", "shared": True},
]
SHARED_UNITS = {item["name"] for item in SERVICE_UNITS if item["shared"]}


def _today() -> date:
    return date.today()


def refresh_status(entry: dict[str, Any]) -> str:
    """按归属合同当前的金额与到期日期重新判定履约状态。

    判定顺序：已终止不复活 → 手动标记到期（到期日改期后解除）→ 按到期日期判到期
    → 已签订且金额有效则履行中 → 否则待签订。列表/详情/概览都走这一处。
    """
    if entry.get("terminated"):
        status = STATUS_TERMINATED
    elif entry.get("forced_expired"):
        status = STATUS_EXPIRED
    else:
        expired = False
        due_raw = str(entry.get("到期日期") or "").strip()
        if due_raw:
            try:
                expired = date.fromisoformat(due_raw) < _today()
            except ValueError:
                expired = False
        if expired:
            status = STATUS_EXPIRED
        elif entry.get("signed") and _valid_amount(entry.get("合同金额")):
            status = STATUS_SIGNED
        else:
            status = STATUS_UNSIGNED
    entry["status"] = status
    # 待处理只保留还在履约链路里的：已到期、已终止都不再挂起
    entry["pending"] = status in (STATUS_UNSIGNED, STATUS_SIGNED)
    entry["abnormal"] = status == STATUS_EXPIRED
    return status


def _valid_amount(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _owner(entry: dict[str, Any]) -> str:
    return str(entry.get(OWNER_FIELD) or "").strip()


def is_shared_owner(owner: str) -> bool:
    return owner in SHARED_UNITS


class ContractService:
    # ---------- 服务单位名录 ----------
    def list_units(self) -> list[dict[str, Any]]:
        return [dict(item) for item in SERVICE_UNITS]

    # ---------- 读取与可见范围 ----------
    def list_entries(
        self,
        *,
        unit: str | None = None,
        scope: str = "mine",
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        """返回 (分页数据, 总数, 统计)。可见范围由 scope 决定：

        mine=本单位合同（归属缺失的不可见）；missing=归属缺失待认领；
        shared=共用服务单位只读合同。
        """
        rows = store.rows(MODULE)
        scoped: list[dict[str, Any]] = []
        for row in rows:
            owner = _owner(row)
            if scope == "missing":
                if not owner:
                    scoped.append(row)
            elif scope == "shared":
                if is_shared_owner(owner):
                    scoped.append(row)
            else:
                if owner and owner == unit:
                    scoped.append(row)
        if keyword:
            scoped = [row for row in scoped if keyword in str(row.get("合同编号", ""))]
        if status:
            scoped = [row for row in scoped if refresh_status(row) == status]
        # 统计口径取当前可见范围，但履约状态全部来自 refresh_status 这同一份
        summary = self._summarize(scoped)
        total = len(scoped)
        start = max(page - 1, 0) * size
        items = [self.present(row, unit=unit) for row in scoped[start:start + size]]
        return items, total, summary

    def _summarize(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        active = expired = unsigned = 0
        total_amount = 0.0
        for row in rows:
            status = refresh_status(row)
            if status == STATUS_SIGNED:
                active += 1
            elif status == STATUS_EXPIRED:
                expired += 1
            elif status == STATUS_UNSIGNED:
                unsigned += 1
            try:
                total_amount += float(row.get("合同金额") or 0)
            except (TypeError, ValueError):
                pass
        return {
            "active": active,
            "expired": expired,
            "unsigned": unsigned,
            "missing": self.count_missing(),
            "totalAmount": round(total_amount, 2),
        }

    def count_missing(self) -> int:
        return sum(1 for row in store.rows(MODULE) if not _owner(row))

    def count_active(self) -> int:
        """运营概览的在履合同数：全平台范围内履约状态为履行中的合同。"""
        return sum(1 for row in store.rows(MODULE) if refresh_status(row) == STATUS_SIGNED)

    def get_entry(self, entry_id: int, *, unit: str | None = None) -> tuple[dict[str, Any] | None, str]:
        """详情同样受归属范围约束：别家单位的合同只读范围之外，直接拦下。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        owner = _owner(entry)
        if not owner:
            return self.present(entry, unit=unit), ""
        if is_shared_owner(owner):
            return self.present(entry, unit=unit, readonly_override=True), ""
        if unit != owner:
            return None, f"合同归属「{owner}」，当前服务单位「{unit or '未选择'}」无权查看，跨单位访问已拦截"
        return self.present(entry, unit=unit), ""

    def get_history(self, entry_id: int, *, unit: str | None = None) -> tuple[list[dict[str, Any]], str]:
        entry, message = self.get_entry(entry_id, unit=unit)
        if entry is None:
            return [], message
        rows = [
            dict(row) for row in store.rows(HISTORY_MODULE)
            if int(row.get("合同ID", 0)) == entry_id
        ]
        rows.sort(key=lambda row: (str(row.get("时间", "")), int(row.get("id", 0))))
        return rows, ""

    def present(self, entry: dict[str, Any], *, unit: str | None = None, readonly_override: bool = False) -> dict[str, Any]:
        """对外展示统一补一份派生字段，杜绝列表与详情各算各的。"""
        view = dict(entry)
        owner = _owner(entry)
        view["履约状态"] = refresh_status(entry)
        view["归属缺失"] = not owner
        if readonly_override:
            view["只读"] = True
        elif not owner:
            view["只读"] = True  # 归属缺失：认领前只允许只读查看
        elif is_shared_owner(owner):
            view["只读"] = True
        elif unit != owner:
            view["只读"] = True
        else:
            view["只读"] = False
        return view

    # ---------- 写入前的归属拦截 ----------
    def _guard_writable(
        self, entry: dict[str, Any], unit: str | None, *, allow_missing_claim: bool = False
    ) -> str:
        owner = _owner(entry)
        if not owner:
            if allow_missing_claim:
                return ""
            return "该合同归属缺失，需先由服务单位认领归属后才能改动"
        if is_shared_owner(owner):
            return f"「{owner}」是集团共用服务单位，合同信息全平台只读，不能改动"
        if not unit:
            return "未选择当前服务单位，无法判定归属，操作已拦截"
        if unit != owner:
            return f"合同归属「{owner}」，当前服务单位「{unit}」无权改动，跨单位操作已拦截"
        return ""

    @staticmethod
    def _guard_unit(unit: str | None) -> str:
        if not unit:
            return "未选择当前服务单位，无法按归属登记合同"
        if is_shared_owner(unit):
            return f"「{unit}」是集团共用服务单位，共用名录只读，不能把合同登记到该单位名下"
        if unit not in {item["name"] for item in SERVICE_UNITS}:
            return f"服务单位「{unit}」不在单位名录中，请先确认归属"
        return ""

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any], unit: str | None) -> tuple[dict[str, Any] | None, str]:
        message = self._guard_unit(unit)
        if message:
            return None, message
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("合同编号") or "").strip()
        if any(str(row.get("合同编号") or "") == code for row in store.rows(MODULE)):
            return None, f"合同编号「{code}」已存在，请核对后再登记"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": store.next_id(MODULE)}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 登记时强制按当前服务单位归属，不允许替别家单位登记
        entry[OWNER_FIELD] = unit
        for field in EDITABLE_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["signed"] = False
        entry["forced_expired"] = False
        entry["terminated"] = False
        refresh_status(entry)
        rows.append(entry)
        self._log(entry, unit, "登记合同", f"合同登记到「{unit}」名下")
        return self.present(entry, unit=unit), ""

    # ---------- 状态动作 ----------
    def run_action(self, entry_id: int, action: str, unit: str | None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        blocked = self._guard_writable(entry, unit)
        if blocked:
            return None, blocked
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于维保合同可执行范围"
        flag = ACTION_RULES[action]
        if entry.get("terminated"):
            return None, "合同已终止，终止后的合同不能再执行状态动作"
        if action == "确认签订":
            entry["signed"] = True
        elif action == "标记到期":
            entry["forced_expired"] = True
        elif action == "终止合同":
            entry["terminated"] = True
        status = refresh_status(entry)
        self._log(entry, unit, action, f"履约状态判定为「{status}」")
        return self.present(entry, unit=unit), f"维保合同已{action}，履约状态：{status}"

    # ---------- 金额 / 到期日期调整 ----------
    def adjust_entry(self, entry_id: int, values: dict[str, Any], unit: str | None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        blocked = self._guard_writable(entry, unit)
        if blocked:
            return None, blocked
        changes: list[str] = []
        if "合同金额" in values and values["合同金额"] is not None:
            try:
                amount = float(values["合同金额"])
            except (TypeError, ValueError):
                return None, "合同金额必须是数字，本次调整未生效"
            if amount < 0:
                return None, "合同金额不能为负，本次调整未生效"
            entry["合同金额"] = amount
            changes.append(f"合同金额→{amount:g}")
        if "到期日期" in values and values["到期日期"] is not None:
            due = str(values["到期日期"]).strip()
            try:
                date.fromisoformat(due)
            except ValueError:
                return None, "到期日期需为 YYYY-MM-DD 格式，本次调整未生效"
            entry["到期日期"] = due
            # 到期日期重新约定后，之前的手动到期标记解除，按新日期重判
            entry["forced_expired"] = False
            changes.append(f"到期日期→{due}")
        if not changes:
            return None, "没有可调整的合同金额或到期日期"
        status = refresh_status(entry)
        self._log(entry, unit, "调整合同", "；".join(changes) + f"，履约状态重判为「{status}」")
        return self.present(entry, unit=unit), f"已调整{ '、'.join(changes) }，履约状态按归属重判为「{status}」"

    # ---------- 归属变更（含缺失认领）----------
    def change_owner(self, entry_id: int, target_unit: str | None, unit: str | None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        target = str(target_unit or "").strip()
        if not target:
            return None, "未提供目标服务单位，归属变更未生效"
        if is_shared_owner(target):
            return None, f"「{target}」是集团共用服务单位，共用名录只读，不能把合同划归共用单位"
        if target not in {item["name"] for item in SERVICE_UNITS}:
            return None, f"目标服务单位「{target}」不在单位名录中"
        current = _owner(entry)
        if current == target:
            return None, f"合同本就归属「{target}」，无需变更"
        if current:
            # 已归属合同的变更属于跨单位改动：只有原归属单位自己能发起
            blocked = self._guard_writable(entry, unit)
            if blocked:
                return None, blocked
            reason = f"归属由「{current}」变更为「{target}」，历史履约记录保留在「{current}」名下"
            action = "变更归属"
        else:
            # 归属缺失：任一名录内单位可认领
            if not unit:
                return None, "未选择当前服务单位，无法认领归属缺失合同"
            reason = f"归属缺失合同由「{target}」认领，认领前记录保留在「归属缺失」名下"
            action = "认领归属"
        entry[OWNER_FIELD] = target
        status = refresh_status(entry)
        # 注意：历史按变更后的归属快照追加，但旧记录不动——留在原服务单位名下
        self._log(entry, target, action, reason + f"，履约状态：{status}")
        return self.present(entry, unit=target), f"{action}成功：{reason}"

    # ---------- 删除（引用拦截）----------
    def referenced_by_other_units(self, entry: dict[str, Any]) -> list[str]:
        """找出引用了该合同、且归属不是本合同单位的别家单位。"""
        code = str(entry.get("合同编号") or "")
        owner = _owner(entry)
        others: set[str] = set()
        for row in store.rows(SETTLE_MODULE):
            ref = str(row.get("关联合同") or "").strip()
            if not ref or ref != code:
                continue
            ref_owner = str(row.get(REF_OWNER_FIELD) or "").strip()
            if ref_owner and ref_owner != owner:
                others.add(ref_owner)
        return sorted(others)

    def delete_entry(self, entry_id: int, unit: str | None) -> tuple[bool, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return False, f"维保合同 {entry_id} 不存在或已归档"
        blocked = self._guard_writable(entry, unit)
        if blocked:
            return False, blocked
        others = self.referenced_by_other_units(entry)
        if others:
            return False, (
                f"合同已被别家单位（{'、'.join(others)}）的结算单引用，不能直接删除；"
                "请先解除引用或联系引用单位处理"
            )
        code = str(entry.get("合同编号") or "")
        owner = _owner(entry)
        store.delete(MODULE, entry_id)
        # 历史履约记录不随合同主档删除，仍留在原服务单位名下可查
        history = store.rows(HISTORY_MODULE)
        for row in history:
            if int(row.get("合同ID", 0)) == entry_id and not row.get("主档已删除"):
                row["主档已删除"] = True
        self._log(
            {"id": entry_id, "合同编号": code, OWNER_FIELD: owner},
            owner,
            "删除合同",
            f"合同主档已由「{owner}」删除，履约历史保留在原归属名下",
            deleted=True,
        )
        return True, "合同已删除，历史履约记录仍保留在原服务单位名下"

    # ---------- 履约历史（归属快照留痕）----------
    def _log(
        self,
        entry: dict[str, Any],
        unit: str | None,
        action: str,
        detail: str,
        *,
        deleted: bool = False,
    ) -> None:
        history = store.rows(HISTORY_MODULE)
        record = {
            "id": store.next_id(HISTORY_MODULE),
            "合同ID": entry.get("id"),
            "合同编号": entry.get("合同编号"),
            "动作": action,
            "说明": detail,
            UNIT_FIELD: unit or "归属缺失",
            "时间": _today().isoformat(),
        }
        if deleted:
            record["主档已删除"] = True
        history.append(record)


# 供 store.overview 注入的统一口径
STATUS_REFRESHERS: dict[str, Callable[[dict[str, Any]], str]] = {MODULE: refresh_status}

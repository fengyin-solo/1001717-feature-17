"""维保合同业务规则：履约可见范围、归属校验、状态重判与筛选口径都收在这里。

口径约定（列表、详情、运营概览共用同一份）：
- 合同按「服务单位」归属；本单位只能维护归属本单位的合同。
- 归属为「共用服务单位」的合同所有单位只读可见，任何单位都不能改动。
- 服务单位缺失的合同单独列出，需先由某个单位认领补录归属后才能维护。
- 履约状态只由合同自身事实派生：已终止 > 已到期 > 履行中 > 待签订；
  调整合同金额、到期日期或执行动作后都会重新判定。
- 结算单是合同的履约记录，创建时快照归属单位；归属变更后历史记录仍留在原单位。
- 已有履约记录（结算单）引用的合同不能直接删除。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import settings
from app.store import store

MODULE = "contract"
SETTLE_MODULE = "settle"
REQUIRED_FIELDS = ["合同编号", "维保设备"]
OWNER_FIELD = "服务单位"
EDITABLE_FIELDS = ["合同编号", "维保设备", "合同金额", "服务期限", "签订人员", "到期日期"]

STATUS_PENDING = "待签订"
STATUS_ACTIVE = "履行中"
STATUS_EXPIRED = "已到期"
STATUS_TERMINATED = "已终止"
STATUS_ORDER = [STATUS_PENDING, STATUS_ACTIVE, STATUS_EXPIRED, STATUS_TERMINATED]
ACTION_RULES = {"确认签订": "sign", "标记到期": "expire", "终止合同": "terminate"}


class ScopeError(PermissionError):
    """跨单位改动共用/他单位合同时抛出，消息即给用户看的拦截原因。"""


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def derive_status(entry: dict[str, Any], *, today: date | None = None) -> str:
    """履约状态唯一判定入口：列表、详情、概览都从这里取，避免多处口径漂移。"""
    today = today or date.today()
    if entry.get("terminated"):
        return STATUS_TERMINATED
    end_date = _parse_date(entry.get("到期日期"))
    # 手动「标记到期」或到期日期已过，都算已到期。
    if entry.get("force_expired") or (end_date is not None and end_date < today):
        return STATUS_EXPIRED
    # 已签订（确认签订后置位）且金额为正，才算真正在履；未签订一律待签订。
    if entry.get("signed"):
        amount = _parse_amount(entry.get("合同金额"))
        if amount is not None and amount > 0:
            return STATUS_ACTIVE
    return STATUS_PENDING


def derive_abnormal(entry: dict[str, Any], *, today: date | None = None) -> bool:
    """异常提示：金额不是正数，或在履合同临近到期（默认 30 天内）。"""
    today = today or date.today()
    amount = _parse_amount(entry.get("合同金额"))
    if amount is None or amount <= 0:
        return True
    if derive_status(entry, today=today) == STATUS_ACTIVE:
        end_date = _parse_date(entry.get("到期日期"))
        if end_date is None or end_date <= today + timedelta(days=settings.expiring_days):
            return True
    return False


def owner_of(entry: dict[str, Any]) -> str:
    return str(entry.get(OWNER_FIELD) or "").strip()


class ContractService:
    def __init__(self) -> None:
        # 归属变更流水：记录合同每次归属调整，历史履约记录凭结算单上的归属快照留档。
        self._ownership_log: list[dict[str, Any]] = []

    # ---- 归属与可见范围 -------------------------------------------------

    def resolve_unit(self, unit: str | None) -> str:
        """请求头传的是单位编码（Latin-1），这里统一翻译成单位名称再参与归属判断。"""
        code = str(unit or "").strip()
        if not code:
            return settings.unit_name(settings.default_unit)
        return settings.unit_name(code)

    def list_units(self) -> dict[str, Any]:
        return {
            "units": [{"code": code, "name": name} for code, name in settings.units],
            "default": settings.default_unit,
            "shared": {"code": settings.shared_unit, "name": settings.shared_name},
        }

    def scope_of(self, entry: dict[str, Any], viewer: str) -> str:
        owner = owner_of(entry)
        if not owner:
            return "missing"
        if owner == settings.shared_name:
            return "shared"
        if owner == viewer:
            return "mine"
        # 已转出合同：原单位仍可只读查看留在自己名下的历史履约记录，但不能再维护。
        if any(
            str(item.get("原归属") or "") == viewer
            and int(item.get("合同ID", 0)) == int(entry.get("id", 0))
            for item in self._ownership_log
        ):
            return "legacy"
        return "other"

    def _ensure_can_view(self, entry: dict[str, Any], viewer: str) -> None:
        if self.scope_of(entry, viewer) == "other":
            raise ScopeError(
                f"合同归属「{owner_of(entry)}」，{viewer}无权查看，仅能查看本单位、共用、归属缺失或已转出的合同"
            )

    def _ensure_can_edit(self, entry: dict[str, Any], viewer: str, *, action: str = "改动") -> None:
        owner = owner_of(entry)
        if not owner:
            raise ScopeError(
                f"该合同缺少归属服务单位，请先由本单位认领补录归属后再{action}"
            )
        if owner == settings.shared_name:
            raise ScopeError(
                f"合同归属「{settings.shared_name}」，属各单位共用档案，只读不可{action}"
            )
        if owner != viewer:
            if self.scope_of(entry, viewer) == "legacy":
                raise ScopeError(
                    f"合同已转出至「{owner}」，{viewer}只能只读查看留在本单位名下的历史履约记录，不能再改动"
                )
            raise ScopeError(
                f"合同归属「{owner}」，{viewer}不能跨单位{action}；"
                "如需调整请联系归属单位，或由归属单位发起归属变更"
            )

    def decorate(self, entry: dict[str, Any], viewer: str) -> dict[str, Any]:
        """给记录补上统一口径的履约状态与归属标记，列表和详情用的是同一份结果。"""
        status = derive_status(entry)
        owner = owner_of(entry)
        scope = self.scope_of(entry, viewer)
        return {
            **entry,
            "status": status,
            "pending": status == STATUS_ACTIVE,
            "abnormal": derive_abnormal(entry),
            "归属单位": owner or None,
            "scope": scope,
            "readonly": scope in ("shared", "other", "legacy"),
            "can_maintain": scope == "mine",
        }

    # ---- 查询 -----------------------------------------------------------

    def list_entries(
        self,
        *,
        unit: str | None = None,
        scope: str = "mine",
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        viewer = self.resolve_unit(unit)
        if scope not in ("mine", "shared", "missing", "legacy", "all_visible"):
            scope = "mine"
        rows: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            row_scope = self.scope_of(row, viewer)
            visible = row_scope != "other"
            if not visible:
                continue
            if scope != "all_visible" and row_scope != scope:
                continue
            if keyword and keyword not in str(row.get("合同编号", "")):
                continue
            decorated = self.decorate(row, viewer)
            if status and decorated["status"] != status:
                continue
            rows.append(decorated)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int, *, unit: str | None = None) -> dict[str, Any] | None:
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        self._ensure_can_view(entry, viewer)
        result = self.decorate(entry, viewer)
        result["履约记录"] = self.list_fulfillments(entry_id, unit=unit)
        result["归属变更"] = [
            item for item in self._ownership_log if int(item.get("合同ID", 0)) == entry_id
        ]
        return result

    def summary(self, *, unit: str | None = None) -> dict[str, int]:
        """合同看板指标：与列表/详情共用 decorate 的状态口径。"""
        viewer = self.resolve_unit(unit)
        rows = [
            self.decorate(row, viewer)
            for row in store.rows(MODULE)
            if self.scope_of(row, viewer) != "other"
        ]
        mine = [row for row in rows if row["scope"] == "mine"]
        total_amount = 0.0
        for row in mine:
            amount = _parse_amount(row.get("合同金额"))
            if amount is not None:
                total_amount += amount
        return {
            "本单位合同": len(mine),
            "在履合同": sum(1 for row in rows if row["status"] == STATUS_ACTIVE and row["scope"] == "mine"),
            "临近到期": sum(1 for row in mine if self._is_expiring(row)),
            "共用合同": sum(1 for row in rows if row["scope"] == "shared"),
            "归属缺失": sum(1 for row in rows if row["scope"] == "missing"),
            "合同总金额": int(total_amount) if total_amount.is_integer() else round(total_amount, 2),
        }

    @staticmethod
    def _is_expiring(row: dict[str, Any], *, today: date | None = None) -> bool:
        today = today or date.today()
        if row["status"] != STATUS_ACTIVE:
            return False
        end_date = _parse_date(row.get("到期日期"))
        return end_date is not None and today <= end_date <= today + timedelta(days=settings.expiring_days)

    # ---- 写入 -----------------------------------------------------------

    def create_entry(self, values: dict[str, Any], *, unit: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
        viewer = self.resolve_unit(unit)
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        # 新登记合同一律归属当前单位；共用档案不能通过登记直接产生。
        submitted_owner = str(values.get(OWNER_FIELD) or "").strip()
        if submitted_owner and submitted_owner != viewer:
            raise ScopeError(
                f"新登记合同只能归属当前单位「{viewer}」，不能直接登记到「{submitted_owner}」名下"
            )
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in EDITABLE_FIELDS})
        entry[OWNER_FIELD] = viewer
        entry["signed"] = False
        entry["terminated"] = False
        entry["force_expired"] = False
        rows.append(entry)
        return self.decorate(entry, viewer), []

    def update_entry(
        self, entry_id: int, values: dict[str, Any], *, unit: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        self._ensure_can_edit(entry, viewer, action="修改")
        # 归属只能走专门的归属变更动作，普通编辑里夹带服务单位一律拦下。
        if OWNER_FIELD in values and str(values.get(OWNER_FIELD) or "").strip() != owner_of(entry):
            return None, (
                f"合同归属不能随字段编辑改动；如需从「{owner_of(entry)}」划出，"
                "请使用「归属变更」并说明接收单位"
            )
        for field in EDITABLE_FIELDS:
            if field == OWNER_FIELD:
                continue
            if field in values:
                entry[field] = values[field]
        # 到期日期一旦重新约定，此前的手动到期标记失效，状态按新日期重判。
        if "到期日期" in values:
            entry["force_expired"] = False
        # 金额或到期日期变化后，履约状态按归属口径重新判定，不保留旧标签。
        return self.decorate(entry, viewer), "维保合同已更新，履约状态已按最新金额与到期日期重新判定"

    def run_action(
        self, entry_id: int, action: str, *, unit: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于维保合同可执行范围"
        self._ensure_can_edit(entry, viewer, action=action)
        kind = ACTION_RULES[action]
        if kind == "sign":
            entry["signed"] = True
            entry["terminated"] = False
            entry["force_expired"] = False
        elif kind == "expire":
            # 直接标记到期只置事实位；通常到期由到期日期自动判定。
            entry["force_expired"] = True
        elif kind == "terminate":
            entry["terminated"] = True
        status = derive_status(entry)
        return self.decorate(entry, viewer), f"维保合同已{action}，当前履约状态：{status}"

    def transfer_ownership(
        self, entry_id: int, target_unit: str, *, unit: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """归属变更：只有当前归属单位能发起；变更后历史履约记录仍留在原单位。"""
        viewer = self.resolve_unit(unit)
        target = str(target_unit or "").strip()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        self._ensure_can_edit(entry, viewer, action="变更归属")
        if not target:
            return None, "请选择接收的服务单位"
        if target == settings.shared_unit or target == settings.shared_name:
            return None, "不能把合同划入共用服务单位，共用档案只读不承接具体合同"
        target_name = settings.unit_name(target)
        if target not in settings.unit_codes:
            return None, f"「{target}」不在可承接的服务单位名单内"
        if target_name == owner_of(entry):
            return None, f"合同本就归属「{target_name}」，无需变更"
        old_owner = owner_of(entry)
        entry[OWNER_FIELD] = target_name
        self._ownership_log.append({
            "合同ID": entry_id,
            "合同编号": entry.get("合同编号"),
            "原归属": old_owner,
            "新归属": target_name,
            "操作单位": viewer,
            "变更日期": str(date.today()),
        })
        return self.decorate(entry, viewer), (
            f"合同归属已由「{old_owner}」变更为「{target_name}」；"
            f"变更前的历史履约记录仍保留在「{old_owner}」名下"
        )

    def claim_ownership(
        self, entry_id: int, *, unit: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """归属缺失的合同：由当前单位认领补录归属，认领后才能维护。"""
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"维保合同 {entry_id} 不存在或已归档"
        if owner_of(entry):
            return None, f"合同已归属「{owner_of(entry)}」，不能重复认领"
        entry[OWNER_FIELD] = viewer
        self._ownership_log.append({
            "合同ID": entry_id,
            "合同编号": entry.get("合同编号"),
            "原归属": None,
            "新归属": viewer,
            "操作单位": viewer,
            "变更日期": str(date.today()),
        })
        return self.decorate(entry, viewer), f"归属缺失合同已由「{viewer}」认领并补录归属"

    def delete_entry(self, entry_id: int, *, unit: str | None = None) -> tuple[bool, str]:
        """删除合同：共用/他单位合同拦下；已被结算单引用的合同不能直接删除。"""
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return False, f"维保合同 {entry_id} 不存在或已归档"
        self._ensure_can_edit(entry, viewer, action="删除")
        refs = self.references(entry_id)
        if refs:
            other = [ref for ref in refs if ref["履约单位"] not in ("", viewer)]
            reason = (
                f"已被「{ '、'.join(sorted({ref['履约单位'] for ref in other})) }」等单位的履约记录引用"
                if other else "已有本单位的履约记录引用"
            )
            return False, (
                f"合同「{entry.get('合同编号')}」{reason}（共 {len(refs)} 条结算单），"
                "不能直接删除；请先处置相关结算单后再试"
            )
        store.rows(MODULE).remove(entry)
        self._ownership_log = [
            item for item in self._ownership_log if int(item.get("合同ID", 0)) != entry_id
        ]
        return True, "维保合同已删除"

    # ---- 履约记录（结算单引用） ----------------------------------------

    def references(self, entry_id: int) -> list[dict[str, Any]]:
        """返回引用该合同的结算单；结算单创建时快照的履约单位就是历史归属依据。"""
        code = str((store.find(MODULE, entry_id) or {}).get("合同编号") or "")
        refs: list[dict[str, Any]] = []
        for row in store.rows(SETTLE_MODULE):
            if str(row.get("关联合同") or "").strip() == code:
                refs.append({
                    "结算单号": row.get("结算单号"),
                    "履约单位": str(row.get("履约单位") or "").strip(),
                    "结算状态": row.get("status"),
                })
        return refs

    def list_fulfillments(self, entry_id: int, *, unit: str | None = None) -> list[dict[str, Any]]:
        viewer = self.resolve_unit(unit)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return []
        refs = self.references(entry_id)
        # 归属变更后旧记录仍挂在原单位名下：本单位只能看到本单位快照的历史履约记录。
        return [ref for ref in refs if ref["履约单位"] in ("", viewer)]

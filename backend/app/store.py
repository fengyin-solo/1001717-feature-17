"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        # 合同模块的 pending/abnormal 按履约状态派生口径重算，保证与列表、详情一致。
        from app.services.contract import (
            MODULE as CONTRACT_MODULE,
            STATUS_ACTIVE,
            derive_abnormal,
            derive_status,
        )

        modules: list[dict[str, object]] = []
        active_contracts = 0
        for name in self.module_names():
            rows = self.rows(name)
            if name == CONTRACT_MODULE:
                pending = sum(1 for row in rows if derive_status(row) == STATUS_ACTIVE)
                abnormal = sum(1 for row in rows if derive_abnormal(row))
                active_contracts = pending
            else:
                pending = sum(1 for row in rows if row.get("pending"))
                abnormal = sum(1 for row in rows if row.get("abnormal"))
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": pending,
                "abnormal": abnormal,
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
            # 在履合同数：与维保合同列表、详情的履约状态取同一份派生结果。
            {"label": "在履合同数", "value": active_contracts},
        ]
        return {"cards": cards, "modules": modules}


store = Store()

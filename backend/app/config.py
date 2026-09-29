"""运行配置：端口、跨域、运行环境。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    app_name: str = "特种设备点检运维平台"
    env: str = "local"
    port: int = 8000
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200
    # 维保合同履约可见范围：单位编码 -> 名称（HTTP 头只能传 Latin-1，所以用编码）。
    units: tuple[tuple[str, str], ...] = (
        ("unit-1", "一车间"),
        ("unit-2", "二车间"),
        ("unit-3", "三车间"),
    )
    default_unit: str = "unit-1"
    shared_unit: str = "shared"

    @property
    def unit_codes(self) -> tuple[str, ...]:
        return tuple(code for code, _ in self.units)

    @property
    def unit_names(self) -> tuple[str, ...]:
        return tuple(name for _, name in self.units)

    def unit_name(self, code: str) -> str:
        return dict(self.units).get(code, code)

    def unit_code(self, name: str) -> str | None:
        return {name: code for code, name in self.units}.get(name)

    @property
    def shared_name(self) -> str:
        return "共用服务单位"

    expiring_days: int = 30


settings = Settings()

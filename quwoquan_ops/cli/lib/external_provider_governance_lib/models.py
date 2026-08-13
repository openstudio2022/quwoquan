"""治理 issue 数据模型（原单文件逐字搬运）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderGovernanceIssue:
    location: str
    message: str

    def render(self) -> str:
        return f"{self.location}: {self.message}"

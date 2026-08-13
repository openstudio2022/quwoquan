"""page_object_contract 路径同步的常量与结果模型。

本模块承载同步工具的全部路径常量、结果数据类与契约错误类型；
逻辑真相源仍是薄入口 ``sync_page_object_source_paths.py`` 声明的行为契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# 本模块位于 contracts/page_object_source_paths/ 包内，比原单文件深一层，
# 仓库根因此是 parents[4]（原文件为 parents[3]）。
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
APP_DIR_NAME = "quwoquan_app"
CONTRACT_REL = "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"

#: 搬迁流每 15~30 秒提交一次，重命名链可能跨多个提交，逐跳追到磁盘存在为止。
GIT_RENAME_MAX_HOPS = 8

#: 与 ``source_path`` 一样承载 App 相对路径、同样会被搬迁打断的装配证据字段。
EVIDENCE_FIELDS = ("route_registration_evidence", "mount_evidence")

#: 运行报告目录名；落在 `.qwq_output` 下，可删除可重建，不是第二套页面台账。
REPORT_DIR_NAME = "page-object-source-path"


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcePathFix:
    """一条已被唯一确定并修正的 App 相对路径。"""

    page_id: str
    field_name: str
    old_path: str
    new_path: str
    method: str


@dataclass(frozen=True)
class ManualDecision:
    """无法唯一确定、必须人工裁决的条目。"""

    page_id: str
    field_name: str
    old_path: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewFinding:
    """不阻断 source_path 收敛、但必须人工看见的伴生风险。"""

    kind: str
    page_id: str
    source_path: str
    detail: str


@dataclass
class SyncReport:
    total_pages: int = 0
    fixes: list[SourcePathFix] = field(default_factory=list)
    manual: list[ManualDecision] = field(default_factory=list)
    review: list[ReviewFinding] = field(default_factory=list)
    changed: bool = False

    @property
    def drift_total(self) -> int:
        return len(self.fixes) + len(self.manual)

    def as_json(self) -> dict:
        return {
            "totalPages": self.total_pages,
            "driftTotal": self.drift_total,
            "changed": self.changed,
            "fixes": [
                {
                    "pageId": item.page_id,
                    "field": item.field_name,
                    "oldPath": item.old_path,
                    "newPath": item.new_path,
                    "method": item.method,
                }
                for item in self.fixes
            ],
            "manual": [
                {
                    "pageId": item.page_id,
                    "field": item.field_name,
                    "oldPath": item.old_path,
                    "reason": item.reason,
                    "candidates": list(item.candidates),
                }
                for item in self.manual
            ],
            "review": [
                {
                    "kind": item.kind,
                    "pageId": item.page_id,
                    "sourcePath": item.source_path,
                    "detail": item.detail,
                }
                for item in self.review
            ],
        }


class ContractError(RuntimeError):
    """契约文件本身不可用（结构非法、页面块不可定位等）。"""

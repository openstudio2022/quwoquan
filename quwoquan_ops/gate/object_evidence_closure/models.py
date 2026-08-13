"""缺口/动态判定 dataclass 与路径、摘要归一助手。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .constants import ROOT


@dataclass(frozen=True)
class Gap:
    object_id: str
    kind: str
    stage: str
    dimension: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "objectId": self.object_id,
            "kind": self.kind,
            "stage": self.stage,
            "dimension": self.dimension,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DynamicEvaluation:
    exit_code: int
    report: dict

def display_path(path: Path) -> str:
    """仓内路径显示为相对路径；仓外路径（测试临时目录）原样保留。"""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

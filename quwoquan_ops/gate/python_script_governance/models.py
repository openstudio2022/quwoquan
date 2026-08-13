"""治理报告的记录模型与路径归一。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class Warning:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ScriptRecord:
    path: str
    scope: str
    role: str
    reasons: tuple[str, ...]
    referencedBy: tuple[str, ...]
    importedBy: tuple[str, ...]
    orphanCandidate: bool


@dataclass(frozen=True)
class PythonFileRecord:
    path: str
    scope: str
    boundary: str


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()

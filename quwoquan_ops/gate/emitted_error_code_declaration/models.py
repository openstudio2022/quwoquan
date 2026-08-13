"""发射事实、声明事实与扫描结果的 dataclass 及公共读文件工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Emission:
    code: str
    form: str
    path: str
    function: str


@dataclass(frozen=True)
class ErrorDeclaration:
    code: str
    source_path: str
    go_const: str
    dart_const: str
    surfaces: tuple[str, ...]


@dataclass(frozen=True)
class UnresolvedSite:
    path: str
    function: str
    form: str
    expression: str


@dataclass
class ScanResult:
    emissions: list[Emission] = field(default_factory=list)
    unresolved: list[UnresolvedSite] = field(default_factory=list)
    scanned_files: int = 0


SOURCE_EVIDENCE_SURFACES = frozenset({"http", "gateway", "control_plane", "app"})


@dataclass
class RuntimeErrorVocabulary:
    """从 runtime/errors/errors.go 解析出的 module/kind/reason 常量与 helper 映射。

    不内置回退表：runtime errors 常量只有一个真相源，解析失败必须 fail-fast，
    否则门禁会在真相源改名后静默降级成一张过期的硬编码表。
    """

    modules: dict[str, str]
    kinds: dict[str, str]
    reasons: dict[str, str]
    helpers: dict[str, tuple[str, str]]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

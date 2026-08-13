"""页面对象契约门禁的路径常量、正则与共享小工具（唯一定义处）。

注意：本模块位于 ``scripts/runtime/page/page_object_contract/`` 包内，比原
``verify_page_object_contract.py`` 深一层；``_SCRIPTS_ROOT`` 通过向上探测
``scripts/_common/paths.py`` 定位，不依赖固定 parents 索引，指向值不变。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
# ``page_disk_scan_paths`` 与本包同处 runtime/page concern 目录。
_PAGE_DIR = Path(__file__).resolve().parents[1]
if str(_PAGE_DIR) not in sys.path:
    sys.path.insert(0, str(_PAGE_DIR))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT  # noqa: E402,F401

try:
    import yaml  # type: ignore  # noqa: E402
except ImportError:
    yaml = None  # type: ignore


ROOT = REPO_ROOT
APP = ROOT / "quwoquan_app"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SERVICES = ROOT / "quwoquan_service" / "services"
CONTRACT = METADATA / "_shared" / "page_object_contract.yaml"
ROUTES = METADATA / "_shared" / "app_routes.yaml"
SURFACES = METADATA / "_shared" / "ui_surfaces.yaml"
NAVIGATION_DIR = APP / "lib" / "runtime" / "shell" / "navigation"
ROUTER_DIR = APP / "lib" / "runtime" / "di" / "navigation"
ROUTER_EVIDENCE_PREFIXES = (
    ROUTER_DIR.relative_to(APP).as_posix() + "/",
    NAVIGATION_DIR.relative_to(APP).as_posix() + "/",
)
GENERATED_ROUTES = NAVIGATION_DIR / "generated" / "app_route_paths.g.dart"
GENERATED_SURFACES = NAVIGATION_DIR / "generated" / "app_ui_surfaces.g.dart"
PLATFORM_CAPABILITIES = (
    APP / "lib" / "runtime" / "platform" / "platform_capabilities.dart"
)

PAGE_KINDS = frozenset({"routed", "embedded", "shell", "component", "helper"})
AUTH_REQUIREMENTS = frozenset({"public", "optional", "required", "inherited"})
PAGE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SOURCE_PATH_RE = re.compile(r"^lib/.+\.dart$")
TYPE_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
LOCAL_SLICE_RE = re.compile(r"^local\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
BANNED_PRESENTATION_RE = re.compile(r"(?:\bMap\b|\bdynamic\b|\bGeneric\b)", re.I)
DART_PART_RE = re.compile(
    r"^\s*part\s+['\"]([^'\"]+)['\"]\s*;",
    re.MULTILINE,
)
DART_PART_OF_RE = re.compile(r"^\s*part\s+of\s+", re.MULTILINE)
DART_IMPORT_STATEMENT_RE = re.compile(
    r"^\s*import\s+([^;]+);",
    re.MULTILINE,
)
DART_URI_LITERAL_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return data


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, allow_empty: bool = False) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not allow_empty and not value:
        return None
    if any(not _nonempty_string(item) for item in value):
        return None
    return [str(item).strip() for item in value]


def _snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()

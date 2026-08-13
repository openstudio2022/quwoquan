"""垂类架构防回退门的路径、正则与集合常量（唯一定义处）。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE = (
    ROOT
    / "quwoquan_ops"
    / "policies"
    / "gates"
    / "vertical_architecture_ratchet_baseline.yaml"
)
DOMAIN_TAXONOMY = Path(
    "quwoquan_service/contracts/metadata/_shared/domain_taxonomy.yaml"
)
CONTRACT_GRAPH = Path("quwoquan_service/generated/contract_graph.json")
SERVICE_ROOT = Path("quwoquan_service/services")
RETIRED_TRAVEL_SERVICE = Path("quwoquan_service/services/travel-service")
OUTPUT_ROOT = Path(".qwq_output")
APP_CONTRACT_LOCK = Path(
    "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"
)
APP_GENERATED_MANIFEST = Path(
    "quwoquan_app/tool/cloud_codegen/generated_manifest.json"
)
RETIRED_APP_ARTIFACTS = (
    Path("quwoquan_app/lib/service/travel_service"),
    Path("quwoquan_app/lib/runtime/di/travel_dependencies.dart"),
    Path("quwoquan_app/lib/runtime/di/app_providers_travel.dart"),
    Path("quwoquan_app/lib/runtime/di/navigation/app_router_travel_routes.dart"),
    Path("quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/travel"),
    Path(
        "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/generated/"
        "requests/travel"
    ),
    Path(
        "quwoquan_app/packages/quwoquan_cloud_contracts/lib/generated/"
        "travel_contracts.dart"
    ),
)
TRAVEL_DOMAIN = "travel"

BASELINE_SCHEMA = "vertical-architecture-ratchet"
REQUIRED_BUCKETS = (
    "platform_vertical_branches",
    "content_vertical_usage",
    "domain_taxonomy_runtime_consumers",
)
TRAVEL_DEPENDENCY_AREAS = ("app", "assistant", "api_edge", "runtime", "ops")

CODE_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".js",
    ".kt",
    ".kts",
    ".py",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
TEXT_SUFFIXES = CODE_SUFFIXES | {".json", ".toml", ".yaml", ".yml"}
SKIP_PARTS = {
    ".dart_tool",
    ".git",
    ".qwq_output",
    "__pycache__",
    "build",
    "fixtures",
    "generated",
    "migrations",
    "mock",
    "node_modules",
    "test",
    "testdata",
    "tests",
    "testsupport",
    "vendor",
}
COPY_PARTS = {"l10n"}

CONTENT_VERTICAL_RE = re.compile(r"\b(?:contentVertical|ContentVertical|content_vertical)\b")
TAXONOMY_FILENAME_RE = re.compile(r"\bdomain_taxonomy\.yaml\b")
CASE_RE = re.compile(
    r"(?m)^[ \t]*case[ \t]+(?P<quote>['\"])(?P<value>[a-z][a-z0-9_-]*)"
    r"(?P=quote)[ \t]*(?:,|:|=>)"
)
CONTENT_VERTICAL_COMPARE_RE = re.compile(
    r"(?P<left>\b(?:contentVertical|ContentVertical|content_vertical)\b)"
    r"\s*(?:==|!=)\s*(?P<right>['\"][^'\"]+['\"])"
    r"|(?P<reverse>['\"][^'\"]+['\"])\s*(?:==|!=)\s*"
    r"(?P<identifier>\b(?:contentVertical|ContentVertical|content_vertical)\b)"
)
APP_TRAVEL_DEPENDENCY_RE = re.compile(
    r"package:quwoquan_app/travel/"
    r"|runtime/transport/generated/travel/"
    r"|\btravel-service\b"
    r"|\btravel_service\b"
    r"|\bTravelService\b"
    r"|\bTRAVEL_SERVICE\b"
    r"|\btravel_journey_manager\b"
)
SERVICE_TRAVEL_DEPENDENCY_RE = re.compile(
    r"\btravel-service\b"
    r"|\btravel_service\b"
    r"|\bTravelService\b"
    r"|\bTRAVEL_SERVICE\b"
    r"|\btravel_client\b"
    r"|\bTravelClient\b"
    r"|\btravel\.trip\.[a-z0-9_.-]+\b"
    r"|\btravel_journey_manager\b"
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PATH_RE = re.compile(r"^[a-zA-Z0-9_.@+-]+(?:/[a-zA-Z0-9_.@+-]+)*$")
RETIRED_OUTPUT_NAME_RE = re.compile(
    r"(?:^|[-_])travel-service(?:-materialized)?(?:[._-]|$)"
    r"|^session-c-travel-aside(?:[._-]|$)"
)
RETIRED_APP_OUTPUT_RE = re.compile(
    r"(?:^|/)src/travel(?:/|$)"
    r"|(?:^|/)generated/requests/travel(?:/|$)"
    r"|(?:^|/)generated/travel_contracts\.dart$"
    r"|(?:^|/)travel_operation_contracts\.g(?:\.requests)?\.dart$"
    r"|(?:^|/)travel_(?:api_metadata|request_page_ids)\.g\.dart$"
)

VERTICAL_WORD_STOPLIST = {
    "and",
    "companion",
    "decision",
    "general",
    "planning",
    "the",
    "transport",
    "wellness",
}

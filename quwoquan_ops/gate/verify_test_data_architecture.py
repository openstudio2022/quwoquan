#!/usr/bin/env python3
"""Guard strong typed test-data boundaries and structured fixture budgets.

Trigger: repository gate and direct ``make verify-test-data-architecture``.
Block: weak capability calls, Provider coupling, production imports, oversized or
scenario-dump fixtures, duplicate JSON and environment fixture variants.
Repair: move behavior to typed builders/capabilities, generators, immutable
release references or a manifest/digest-bound benchmark corpus.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t1
spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t2
spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MAX_FIXTURE_BYTES = 64 * 1024
MAX_OBJECT_FIXTURE_BYTES = 256 * 1024
MAX_APP_SUPPORT_FILE_BYTES = 64 * 1024
MAX_APP_SUPPORT_LINE_BYTES = 16 * 1024
MAX_APP_SUPPORT_CONST_JSON_BYTES = 8 * 1024
MAX_SCALAR_LEAVES = 500
MAX_ARRAY_ITEMS = 100
FORBIDDEN_SCENARIO_KEYS = {"seedSets", "repositoryExpectations", "requiresSeedReset"}
CAPABILITY_KEY = re.compile(
    r"^(?:user|content|chat|circle|assistant|notification|rtc)\.[a-z0-9_]+\.[a-z0-9_]+$"
)
RETIRED_TEST_DATA_PATHS = (
    "quwoquan_ops/cli/lib/nonprod_business_data.py",
    "quwoquan_ops/cli/lib/nonprod_data_assistant.py",
    "quwoquan_ops/cli/lib/nonprod_data_evidence.py",
    "quwoquan_ops/cli/lib/nonprod_data_provisioner.py",
    "quwoquan_ops/cli/lib/nonprod_data_verification.py",
    "quwoquan_ops/cli/lib/test_live_business_data.py",
)
RETIRED_TEST_DATA_TOKENS = (
    "--apply-business-data",
    "--nonprod-data-evidence",
    "open_reference_acceptance_session",
    "open_test_live_acceptance_session",
    "materialize_test_live_acceptance_identity_pool",
    "datasetEpoch",
    "test_live_business_data",
)
RETIRED_ENTITY_INTRODUCTION_TOKENS = (
    "entity_scenarios.json",
    "merge_into_scenarios",
    "handle_entity_introduction",
    "def register_parser(",
)
RETIRED_APP_AGGREGATE_TEST_TOKENS = (
    "ChatMockData",
    "CircleMockData",
    "ContentMockData",
    "MockChatRepository",
    "MockContentRepository",
    "PrototypeMockData",
)


def collect_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    issues.extend(_typed_api_issues(root))
    issues.extend(_provider_coupling_issues(root))
    issues.extend(_provider_contract_issues(root))
    issues.extend(_production_purity_issues(root))
    issues.extend(_user_acceptance_fake_issues(root))
    issues.extend(_chat_api_integration_actor_issues(root))
    issues.extend(_eval_corpus_issues(root))
    issues.extend(_scenario_dump_source_issues(root))
    issues.extend(_app_fixture_reader_issues(root))
    issues.extend(_app_support_source_budget_issues(root))
    issues.extend(_fixture_budget_issues(root))
    issues.extend(_generated_provider_state_issues(root))
    issues.extend(_retired_data_track_issues(root))
    return sorted(set(issues))


def _app_fixture_reader_issues(root: Path) -> list[str]:
    """Keep App contract examples object-local and free of filesystem readers."""

    app_test = root / "quwoquan_app/test"
    if not app_test.exists():
        return []
    issues: list[str] = []
    retired_reader = "object_contract_example_reader.dart"
    for path in sorted(app_test.rglob("*.dart")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8", errors="ignore")
        if path.name == retired_reader:
            issues.append(
                f"{relative}: cross-domain object contract fixture reader must be deleted"
            )
        if retired_reader in source:
            issues.append(
                f"{relative}: App tests must use object-local typed builders, "
                "not the retired cross-domain fixture reader"
            )
        if "/test/support/runtime/fixtures/" not in f"/{relative}":
            continue
        if "import 'dart:io'" in source or 'import "dart:io"' in source:
            issues.append(
                f"{relative}: App fixture support must not read contract examples "
                "from the runtime filesystem"
            )
        if "requireExample(" in source or re.search(
            r"\bdocument\s*\(\s*String\s+domain\b",
            source,
        ):
            issues.append(
                f"{relative}: cross-domain named-example fixture matrix is forbidden"
            )
    return issues


def _generated_provider_state_issues(root: Path) -> list[str]:
    """Generated API provider-state must use public commands, never storage setup."""

    relative = Path(
        "quwoquan_service/services/user-service/tests/api_integration/"
        "account/user_account/generated_user_pool_provider_state__api_integration_test.go"
    )
    path = root / relative
    if not path.is_file():
        return []
    source = path.read_text(encoding="utf-8", errors="ignore")
    forbidden = tuple(
        token
        for token in (
            "pgPool",
            "mongoDB",
            "createTestProfile(",
            "createTestPersona(",
            "createTestPersonaFull(",
        )
        if token in source
    )
    if not forbidden:
        return []
    return [
        f"{relative}: generated User provider-state must use public commands; "
        f"storage setup remains: {', '.join(forbidden)}"
    ]


def collect_asset_metrics(root: Path = ROOT) -> dict[str, Any]:
    """Derive asset composition from the current physical tree."""

    handwritten_loc = 0
    builder_generator_loc = 0
    for base in (
        root / "quwoquan_app/test",
        root / "quwoquan_service/services",
        root / "quwoquan_ops/tests",
        root / "quwoquan_data/tests",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".go", ".dart", ".py"}:
                continue
            relative = path.relative_to(root).as_posix()
            lines = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
            is_test = (
                path.name.startswith("test_")
                or "_test." in path.name
                or "__local_contract_test." in path.name
                or "__api_integration_test." in path.name
                or "__user_acceptance_test." in path.name
            )
            if is_test and not path.name.endswith(".g.dart"):
                handwritten_loc += lines
            elif (
                "/test/support/" in relative or "/tests/support/" in relative
            ) and any(
                token in relative.lower()
                for token in ("builder", "factory", "generator", "testobject")
            ):
                builder_generator_loc += lines

    structured = tuple(_structured_test_files(root))
    fixture_bytes = sum(path.stat().st_size for path in structured)
    fixture_loc = sum(
        len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        for path in structured
    )
    release_references = 0
    eval_corpora = tuple(_eval_corpus_files(root))
    for base in (
        root / "quwoquan_ops/cli/lib/test_data/capabilities",
        root / "specs/feature-tree",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            release_references += text.count("immutable release")
            release_references += text.count("ACTIVE_REFERENCE_RELEASE")

    domain_fixture: dict[str, dict[str, int]] = {}
    for domain in ("chat", "content", "user"):
        service_root = (
            root
            / "quwoquan_service/services"
            / f"{domain}-service/tests/support/contract_fixtures"
        )
        paths = tuple(
            path
            for path in service_root.rglob("*")
            if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
        ) if service_root.exists() else ()
        domain_fixture[domain] = {
            "bytes": sum(path.stat().st_size for path in paths),
            "loc": sum(
                len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
                for path in paths
            ),
        }
    return {
        "handwrittenTestLoc": handwritten_loc,
        "staticFixtureLoc": fixture_loc,
        "staticFixtureBytes": fixture_bytes,
        "builderGeneratorLoc": builder_generator_loc,
        "immutableReleaseReferences": release_references,
        "evalCorpusLoc": sum(
            len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
            for path in eval_corpora
        ),
        "evalCorpusBytes": sum(path.stat().st_size for path in eval_corpora),
        "totalTestAssetLoc": handwritten_loc + fixture_loc + builder_generator_loc,
        "targetDomainFixture": domain_fixture,
    }


def _typed_api_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for path in _python_files(root):
        relative = path.relative_to(root).as_posix()
        if "/test" not in relative and not relative.startswith("quwoquan_ops/tests/"):
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            issues.append(f"{relative}:{exc.lineno}: Python syntax error")
            continue
        imports_test_data = any(
            (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith(
                    "quwoquan_ops.cli.lib.test_data"
                )
            )
            or (
                isinstance(node, ast.Import)
                and any(
                    alias.name.startswith("quwoquan_ops.cli.lib.test_data")
                    for alias in node.names
                )
            )
            for node in ast.walk(tree)
        )
        if not imports_test_data:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if ".test_data.providers" in module:
                    issues.append(
                        f"{relative}:{node.lineno}: tests must not import Provider implementations"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if ".test_data.providers" in alias.name:
                        issues.append(
                            f"{relative}:{node.lineno}: tests must not import Provider implementations"
                        )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "bind" and node.args and isinstance(node.args[0], ast.Dict):
                    issues.append(
                        f"{relative}:{node.lineno}: capability params must not be a bare dict"
                    )
                if node.func.attr in {"provision", "provision_all"} and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        issues.append(
                            f"{relative}:{node.lineno}: Session must not accept a capability string"
                        )
            elif isinstance(node, ast.Attribute) and node.attr == "key":
                issues.append(
                    f"{relative}:{node.lineno}: tests must not read internal capability keys"
                )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if CAPABILITY_KEY.fullmatch(node.value):
                    issues.append(
                        f"{relative}:{node.lineno}: tests must not write capability key strings"
                    )
    return issues


def _provider_coupling_issues(root: Path) -> list[str]:
    issues: list[str] = []
    provider_root = root / "quwoquan_ops/cli/lib/test_data/providers"
    for path in sorted(provider_root.glob("*_service.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if node.level == 1 and module not in {"support"}:
                issues.append(
                    f"{path.relative_to(root)}:{node.lineno}: Provider imports a sibling implementation"
                )
            if ".providers." in module and not module.endswith(".providers.support"):
                issues.append(
                    f"{path.relative_to(root)}:{node.lineno}: Provider imports a sibling implementation"
                )
    return issues


def _provider_contract_issues(root: Path) -> list[str]:
    provider_root = root / "quwoquan_ops/cli/lib/test_data/providers"
    graph_path = root / "quwoquan_service/generated/contract_graph.json"
    if root.resolve() != ROOT.resolve() or not provider_root.exists() or not graph_path.is_file():
        return []
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    rows = payload.get("operations") if isinstance(payload, Mapping) else None
    operation_ids = {
        str(row.get("id"))
        for row in rows or []
        if isinstance(row, Mapping) and str(row.get("id") or "")
    }
    issues: list[str] = []
    capability_owners: dict[str, str] = {}
    for path in sorted(provider_root.glob("*_service.py")):
        module = importlib.import_module(
            f"quwoquan_ops.cli.lib.test_data.providers.{path.stem}"
        )
        builder = getattr(module, "build_provider", None)
        if not callable(builder):
            issues.append(
                f"{path.relative_to(root)}: Provider must expose build_provider"
            )
            continue
        definitions = tuple(builder().describe())
        declared_operations = {
            operation_id
            for definition in definitions
            for operation_id in definition.operations
        }
        for definition in definitions:
            owner_service = definition.capability.owner_service
            if owner_service != path.stem:
                issues.append(
                    f"{path.relative_to(root)}: Provider owner {owner_service} "
                    f"does not match module {path.stem}"
                )
            capability_key = definition.capability.key.value
            previous_owner = capability_owners.setdefault(capability_key, path.stem)
            if previous_owner != path.stem:
                issues.append(
                    f"{path.relative_to(root)}: capability {capability_key} "
                    f"is already owned by {previous_owner}"
                )
            for operation_id in definition.operations:
                if operation_id not in operation_ids:
                    issues.append(
                        f"{path.relative_to(root)}: Provider operation is absent "
                        f"from current ContractGraph: {operation_id}"
                    )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used_operations = {
            str(node.args[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"call", "expect_status"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        for operation_id in sorted(used_operations - declared_operations):
            issues.append(
                f"{path.relative_to(root)}: Provider uses operation outside its "
                f"capability definition closure: {operation_id}"
            )
    return issues


def _production_purity_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for base in (root / "quwoquan_app/lib", root / "quwoquan_service/services"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "/tests/" in path.as_posix():
                continue
            if path.suffix not in {".py", ".go", ".dart", ".yaml", ".yml"}:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            if "quwoquan_ops.cli.lib.test_data" in source or "/test_data/" in source:
                issues.append(
                    f"{path.relative_to(root)}: production source references test-data control plane"
                )
    return issues


def _user_acceptance_fake_issues(root: Path) -> list[str]:
    issues: list[str] = []
    base = root / "quwoquan_ops/tests/acceptance/user_acceptance"
    if not base.exists():
        return issues
    for path in sorted(base.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="ignore")
        tokens = tuple(
            token
            for token in ("def _fixture_response", "def built_seed_set")
            if token in source
        )
        if tokens:
            issues.append(
                f"{path.relative_to(root)}: user_acceptance must use production "
                "Remote composition, not a fixture/object-builder gateway"
            )
        if "--fixture-conversation-id" in source:
            issues.append(
                f"{path.relative_to(root)}: user_acceptance must not accept "
                "a fixed fixture conversation identity"
            )
        if re.search(
            r"(?:default\s*=\s*|--(?:viewer|actor|user|persona)-id\s+)"
            r"[\"']?(?:fixture_(?:user|persona)|user_test_)[a-zA-Z0-9_-]*",
            source,
        ):
            issues.append(
                f"{path.relative_to(root)}: user_acceptance must resolve Actor "
                "identity from the active test-data lease"
            )
        if (
            "service_ops/chat-service/" in path.as_posix()
            and re.search(r"\buser_test_[0-9]+\b", source)
        ):
            issues.append(
                f"{path.relative_to(root)}: Chat user_acceptance must resolve "
                "Actor identities from the active test-data lease"
            )
    return issues


def _chat_api_integration_actor_issues(root: Path) -> list[str]:
    """Chat API integration must obtain mutable actors from its test session."""

    issues: list[str] = []
    base = root / "quwoquan_app/test/api_integration/service/chat_service"
    if not base.exists():
        return issues
    actor_pattern = re.compile(r"\buser_test_[A-Za-z0-9_-]+\b")
    for path in sorted(base.rglob("*.dart")):
        if actor_pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            issues.append(
                f"{path.relative_to(root)}: Chat api_integration must resolve "
                "mutable Actor identities from its typed test-data session"
            )
    return issues


def _eval_corpus_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for corpus in _eval_corpus_files(root):
        relative = corpus.relative_to(root)
        manifest = corpus.with_name(corpus.stem + ".manifest.json")
        if not manifest.is_file():
            issues.append(f"{relative}: eval corpus manifest is missing")
            continue
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            payload = json.loads(corpus.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"{relative}:{exc.lineno}: invalid eval corpus JSON")
            continue
        scenarios = payload.get("scenarios") if isinstance(payload, Mapping) else None
        forbidden = sorted(FORBIDDEN_SCENARIO_KEYS & _keys(payload))
        expected_digest = hashlib.sha256(corpus.read_bytes()).hexdigest()
        if metadata.get("schema") != "qwq.eval_corpus_manifest":
            issues.append(f"{manifest.relative_to(root)}: eval corpus schema mismatch")
        if metadata.get("corpusFile") != corpus.name:
            issues.append(f"{manifest.relative_to(root)}: eval corpus filename mismatch")
        if metadata.get("sha256") != expected_digest:
            issues.append(f"{manifest.relative_to(root)}: eval corpus digest drift")
        if not isinstance(scenarios, list) or metadata.get("caseCount") != len(scenarios):
            issues.append(f"{manifest.relative_to(root)}: eval corpus caseCount drift")
        if forbidden:
            issues.append(
                f"{relative}: eval corpus contains retired scenario-data keys: "
                + ", ".join(forbidden)
            )
    return issues


def _scenario_dump_source_issues(root: Path) -> list[str]:
    """Reject old scenario dumps hidden inside language-native test support."""

    issues: list[str] = []
    token_pattern = re.compile(
        r"[\"'](?:seedSets|repositoryExpectations|requiresSeedReset)[\"']"
    )
    app_support = root / "quwoquan_app/test/support"
    if app_support.exists():
        for path in sorted(app_support.rglob("*.dart")):
            if not token_pattern.search(
                path.read_text(encoding="utf-8", errors="ignore")
            ):
                continue
            issues.append(
                f"{path.relative_to(root)}: in-memory builder contains retired "
                "scenario-data keys"
            )
    app_test = root / "quwoquan_app/test"
    if app_test.exists():
        for path in sorted(app_test.rglob("*.dart")):
            source = path.read_text(encoding="utf-8", errors="ignore")
            for token in RETIRED_APP_AGGREGATE_TEST_TOKENS:
                if token in source:
                    issues.append(
                        f"{path.relative_to(root)}: retired aggregate test-data "
                        f"symbol remains: {token}"
                    )
            if re.search(r"\bimplements\s+ChatRepository\b", source):
                issues.append(
                    f"{path.relative_to(root)}: aggregate ChatRepository test "
                    "double is forbidden; override object-level facets"
                )
    data_support = root / "quwoquan_data/tests/support"
    if data_support.exists():
        for path in sorted(data_support.rglob("*.py")):
            source = path.read_text(encoding="utf-8", errors="ignore")
            if token_pattern.search(source):
                issues.append(
                    f"{path.relative_to(root)}: Data test support contains retired "
                    "scenario-data keys"
                )
            if path.name != "entity_introduction_fixture.py":
                continue
            for token in RETIRED_ENTITY_INTRODUCTION_TOKENS:
                if token in source:
                    issues.append(
                        f"{path.relative_to(root)}: retired entity-introduction "
                        f"fixture writer/CLI remains: {token}"
                    )
    return issues


def _app_support_source_budget_issues(root: Path) -> list[str]:
    """Reject giant App support files and JSON corpora hidden in Dart constants."""

    support_root = root / "quwoquan_app/test/support"
    if not support_root.exists():
        return []
    issues: list[str] = []
    const_json_pattern = re.compile(
        r"const\s+String\s+\w+\s*=\s*r?(?P<quote>'''|\"\"\")"
        r"(?P<body>.*?)(?P=quote)\s*;",
        re.DOTALL,
    )
    for path in sorted(support_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        payload = path.read_bytes()
        if len(payload) > MAX_APP_SUPPORT_FILE_BYTES:
            issues.append(
                f"{relative}: App test support file exceeds 64 KiB "
                f"({len(payload)} bytes)"
            )
        largest_line = max((len(line) for line in payload.splitlines()), default=0)
        if largest_line > MAX_APP_SUPPORT_LINE_BYTES:
            issues.append(
                f"{relative}: App test support contains an oversized single line "
                f"({largest_line} bytes); generated/const JSON must use a builder"
            )
        if path.suffix != ".dart":
            continue
        source = payload.decode("utf-8", errors="ignore")
        for match in const_json_pattern.finditer(source):
            body = match.group("body")
            body_size = len(body.encode("utf-8"))
            if body_size <= MAX_APP_SUPPORT_CONST_JSON_BYTES:
                continue
            if not body.lstrip().startswith(("{", "[")):
                continue
            issues.append(
                f"{relative}: App test support const JSON exceeds 8 KiB "
                f"({body_size} bytes); use a deterministic typed builder"
            )
    return issues


def _fixture_budget_issues(root: Path) -> list[str]:
    issues: list[str] = []
    totals: dict[Path, int] = defaultdict(int)
    digests: dict[str, list[Path]] = defaultdict(list)
    for path in _structured_test_files(root):
        relative = path.relative_to(root)
        size = path.stat().st_size
        owner = _object_support_owner(path)
        totals[owner] += size
        if size > MAX_FIXTURE_BYTES:
            issues.append(f"{relative}: structured fixture exceeds 64 KiB ({size} bytes)")
        if re.search(r"\.(?:lite|full|alpha|beta|gamma|prod)(?:[-_.]|$)", path.name):
            issues.append(f"{relative}: environment/full-lite fixture variant is forbidden")
        if path.suffix != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"{relative}:{exc.lineno}: invalid JSON fixture")
            continue
        leaves, largest_array = _shape(payload)
        if leaves > MAX_SCALAR_LEAVES:
            issues.append(f"{relative}: structured fixture has {leaves} scalar leaves (>500)")
        if largest_array > MAX_ARRAY_ITEMS:
            issues.append(f"{relative}: structured fixture array has {largest_array} items (>100)")
        forbidden = sorted(FORBIDDEN_SCENARIO_KEYS & _keys(payload))
        if forbidden:
            issues.append(
                f"{relative}: scenario-dump keys are forbidden: {', '.join(forbidden)}"
            )
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        digests[hashlib.sha256(canonical).hexdigest()].append(relative)
    for owner, total in totals.items():
        if total > MAX_OBJECT_FIXTURE_BYTES:
            issues.append(
                f"{owner.relative_to(root)}: object structured fixtures exceed 256 KiB ({total} bytes)"
            )
    for paths in digests.values():
        if len(paths) > 1:
            issues.append(
                "canonical JSON fixture duplicated: " + ", ".join(str(path) for path in paths)
            )
    return issues


def _retired_data_track_issues(root: Path) -> list[str]:
    """Keep deleted recipe/test-live business-data APIs from returning."""

    issues: list[str] = []
    for relative in RETIRED_TEST_DATA_PATHS:
        if (root / relative).exists():
            issues.append(f"{relative}: retired test-data implementation must be deleted")
    scan_paths: list[Path] = []
    cli_root = root / "quwoquan_ops/cli"
    if cli_root.exists():
        scan_paths.extend(sorted(cli_root.rglob("*.py")))
    specs_root = root / "specs/feature-tree"
    if specs_root.exists():
        scan_paths.extend(sorted(specs_root.rglob("*.md")))
    for path in scan_paths:
        if path.name == Path(__file__).name:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for token in RETIRED_TEST_DATA_TOKENS:
            if token in source:
                issues.append(
                    f"{path.relative_to(root)}: retired test-data token remains: {token}"
                )
    return issues


def _python_files(root: Path) -> Iterable[Path]:
    for base in (root / "quwoquan_ops/tests", root / "quwoquan_service", root / "quwoquan_app"):
        if base.exists():
            yield from sorted(base.rglob("*.py"))


def _structured_test_files(root: Path) -> Iterable[Path]:
    for base in (
        root / "quwoquan_app/test",
        root / "quwoquan_service/services",
        root / "quwoquan_ops/tests",
        root / "quwoquan_data/tests",
    ):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".json", ".yaml", ".yml"}:
                continue
            value = path.as_posix()
            if "/eval_corpora/" in value:
                continue
            if "/test" in value and any(
                token in value for token in ("/fixture", "/fixtures/", "/support/")
            ):
                yield path


def _eval_corpus_files(root: Path) -> Iterable[Path]:
    for base in (root / "quwoquan_service/services", root / "quwoquan_app/test"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("eval_corpora/*.json")):
            if path.name.endswith(".manifest.json"):
                continue
            yield path


def _object_support_owner(path: Path) -> Path:
    parts = path.parts
    if "support" in parts:
        index = parts.index("support")
        return Path(*parts[: index + 1])
    return path.parent


def _shape(value: object) -> tuple[int, int]:
    if isinstance(value, dict):
        rows = [_shape(item) for item in value.values()]
        return sum(row[0] for row in rows), max((row[1] for row in rows), default=0)
    if isinstance(value, list):
        rows = [_shape(item) for item in value]
        return sum(row[0] for row in rows), max(
            [len(value), *(row[1] for row in rows)]
        )
    return 1, 0


def _keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            result.add(str(key))
            result.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_keys(item))
    return result


def main() -> int:
    metrics = collect_asset_metrics()
    print(
        "ASSET_METRICS: "
        f"handwritten_test={metrics['handwrittenTestLoc']} LOC; "
        f"static_fixture={metrics['staticFixtureLoc']} LOC/"
        f"{metrics['staticFixtureBytes']} bytes; "
        f"builder_generator={metrics['builderGeneratorLoc']} LOC; "
        f"eval_corpus={metrics['evalCorpusLoc']} LOC/"
        f"{metrics['evalCorpusBytes']} bytes; "
        f"immutable_release_refs={metrics['immutableReleaseReferences']}; "
        f"total={metrics['totalTestAssetLoc']} LOC"
    )
    for domain, values in metrics["targetDomainFixture"].items():
        print(
            f"ASSET_METRICS[{domain}]: static_fixture="
            f"{values['loc']} LOC/{values['bytes']} bytes"
        )
    issues = collect_issues()
    if issues:
        print(f"GATE_BLOCK: test-data architecture found {len(issues)} issue(s)")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("PASS: strong typed test-data boundaries and fixture budgets are clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""全仓单轨契约零兼容门禁：禁止版本信封、aliases、双读与 warn-only 逃逸。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_ENVELOPE_FIELDS = ("schemaVersion", "contractVersion", "registryRevision")
VERSIONED_SCHEMA_VALUE = re.compile(
    r"(?:/[0-9]+|\.v[0-9]+|\.m[0-9]+|_v[0-9]+)$"
)
# 已知契约身份前缀 + 版本后缀（/N .vN .mN）
VERSIONED_INLINE = re.compile(
    r"\b(?:quwoquan_(?:data|service)|quwoquan\.[A-Za-z0-9_.-]+|"
    r"environment-topology|media-delivery-manifest|local-env-port-manifest|"
    r"prod-plane-access-isolation|legal-static|qwq\.runtime_shared_package|"
    r"app_remote_config|feed_patch|assistant_stream_event|"
    r"qwq-rich-md|release_desired_state|"
    r"content_import_report|homepage_import_report)"
    r"[A-Za-z0-9_.-]*(?:/[0-9]+|\.v[0-9]+|\.m[0-9]+)\b"
)
# schema 字段值带 _vN 后缀（assets / json / yaml）
SCHEMA_VALUE_V_SUFFIX = re.compile(
    r"""["']schema["']\s*:\s*["'][^"']*_v[0-9]+["']"""
)
# schema 身份禁止纯数字 / 语义化数字版本
NUMERIC_SCHEMA_LITERAL = re.compile(
    r"""["']schema["']\s*:\s*(?:[0-9]+(?:\.[0-9]+)?|["'][0-9]+(?:\.[0-9]+)?["'])"""
)
TOP_LEVEL_VERSION = re.compile(r"^version:\s*", re.MULTILINE)
ALIASES_LINE = re.compile(r"^\s+aliases\s*:")
SKIP_EMPTY_ALIASES = re.compile(r"^\s+skip_empty_string_aliases\s*:")
AUTH_REQUIRED_LINE = re.compile(r"^\s+auth_required\s*:")
OPTIONAL_ALIAS_HELPER = re.compile(r"_optionalAliasText|_requiredAliasText")
MAP_LIST_FIRST_PRESENT = re.compile(r"mapListFirstPresent\s*\(")
COMPAT_SMELLS = (
    re.compile(r"Back-compat|back-compat|backward compat|forward compat|forward-compat", re.I),
    re.compile(r"dual-read|dual_read|retired dual-read", re.I),
    re.compile(r"report_dir_compat"),
    re.compile(r"--warn-only"),
    re.compile(r"mode=compat"),
    re.compile(r"legacyMedia"),
)
# 同标识符多键 ??（任意变量名，含 raw?['a']）；键名不同才算双读
MULTI_KEY_DECODE = re.compile(
    r"(?P<ident>\w+)\s*\??\s*\[\s*['\"](?P<k1>[^'\"]+)['\"]\s*\]"
    r"(?:\s*(?:\?\.|\.)\s*toString\(\))?"
    r"(?:\s+as\s+\w+\?)?"
    r"\s*\?\?\s*"
    r"(?P=ident)\s*\??\s*\[\s*['\"](?P<k2>[^'\"]+)['\"]\s*\]"
)
# Go codegen 模板中的双读
MULTI_KEY_GO_TEMPLATE = re.compile(
    r"""json\[['\"][^'\"]+['\"]\][^?\n]{0,40}\?\?\s*json\[['\"][^'\"]+['\"]\]"""
)
# 正向「旧键仍可解析」测试语义（负例须用 rejects/拒绝）
POSITIVE_ALIAS_TEST = re.compile(
    r"(?:_id alias\s*→|_id alias\s*->|仍正确解析|支持\s*_id\s*alias|"
    r"parses counts with aliases|alias\s+used when|"
    r"旧字段名/alias 仍正确解析|旧字段/alias 仍正确解析|"
    r"别名兼容|也能正确投射|alias 必须被 DTO 正确归一|"
    r"likesCount alias 必须被 DTO|"
    r"WireAliases|StillParsed|CompatQueryStill)",
    re.I,
)
# specs / 军规中禁止再教「短期双读 / schemaVersion 契约信封 / 多协议版本」
DOC_DUAL_TRACK_TEACHING = re.compile(
    r"(?:短期双读|允许短期双读|短期并行读取|DTO 解析保留旧字段|feature flag 双读|"
    r"读接口双读|兼容旧字段|兼容存量版本|同时存在三个及以上版本|"
    r"schemaVersion\s*=\s*1|"
    r"支持兼容窗口)",
    re.I,
)
# 客户端 wire 禁止使用 _id 作为 JSON 键（storage/bson 除外）
DART_WIRE_ID_KEY = re.compile(
    r"""(?:m|map|json|obj|raw|root|payload|item|row|data|dm|parsed|e|v)"""
    r"""\s*\??\s*\[\s*['\"]_id['\"]\s*\]"""
)
GO_JSON_ID_TAG = re.compile(r"""json\s*:\s*["']_id["']""")
GO_BSON_ID_TAG = re.compile(r"""bson\s*:\s*["']_id["']""")
GO_MAP_ID_KEY = re.compile(r"""["']_id["']\s*:""")
MULTI_KEY_HELPER_ID = re.compile(
    r"(?:_firstNonEmpty|mapListFirstPresent|mapListFirstNonEmpty)\s*\([^)]*['\"]_id['\"]",
    re.I | re.DOTALL,
)
ID_COMPAT_TEACHING = re.compile(
    r"(?:_id\s*/\s*id\s*兼容|id\s*/\s*_id\s*兼容|api_alias\s*:|"
    r"alias_resolution_mongodb_id|mongodb_id.*alias|_id\s*→\s*id\s*兼容)",
    re.I,
)
NEGATIVE_ID_TEST_LINE = re.compile(
    r"reject|拒绝|forbidden|不得|must not|只认|isEmpty|equals\(\s*''\s*\)|期望.*空",
    re.I,
)

SCAN_ROOTS = (
    "quwoquan_service/contracts",
    "quwoquan_service/tools/codegen_app_metadata",
    "quwoquan_service/internal/metadata",
    "quwoquan_service/services",
    "quwoquan_service/runtime",
    "quwoquan_service/scripts",
    "quwoquan_service/generated",
    "quwoquan_app/lib",
    "quwoquan_app/packages",
    "quwoquan_app/configs",
    "quwoquan_app/scripts",
    "quwoquan_app/assets",
    "quwoquan_app/test",
    "quwoquan_data/schema",
    "quwoquan_data/scripts",
    "quwoquan_data/control_plane",
    "quwoquan_data/templates",
    "quwoquan_data/verticals",
    "quwoquan_data/tests",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
    "quwoquan_ops/gate",
    "quwoquan_ops/tests",
    "quwoquan_ops/portal/src",
    "specs/feature-tree",
    ".cursor/rules",
)

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".dart_tool",
    "build",
    ".qwq_output",
    "vendor",
    "__pycache__",
    ".venv",
}

# 业务语义字段：允许出现，但不允许作为契约多版本信封。
ALLOWED_VERSIONISH_FIELD_NAMES = {
    "expectedVersion",
    "cacheVersion",
    "avatarVersion",
    "policyRevision",
    "profileVersion",
    "thresholdsVersion",
    "sourceRevision",
    "promptBundleRevision",
    "compatibleRuntimeVersion",
    "CONFIG_VERSION",
    "IMAGE_VERSION",
    "openapi",
}

TEXT_SUFFIXES = {
    ".yaml",
    ".yml",
    ".json",
    ".go",
    ".dart",
    ".py",
    ".md",
    ".mdc",
    ".sh",
}


@dataclass
class Finding:
    category: str
    path: str
    detail: str


@dataclass
class Inventory:
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, category: str, path: Path, detail: str) -> None:
        rel = path.relative_to(ROOT).as_posix()
        self.findings.append(Finding(category, rel, detail))
        self.counts[category] += 1


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIR_NAMES)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in TEXT_SUFFIXES:
                continue
            if should_skip(path):
                continue
            files.append(path)
    return sorted(files)


def is_metadata_object_yaml(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if not rel.startswith("quwoquan_service/contracts/metadata/"):
        return False
    if "/_schemas/" in rel or rel.endswith("business_object_map.yaml"):
        return False
    if path.suffix not in {".yaml", ".yml"}:
        return False
    return True


def _is_comment_line(line: str, suffix: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if suffix in {".go", ".dart", ".js", ".ts"} and stripped.startswith("//"):
        return True
    if suffix == ".py" and stripped.startswith("#"):
        return True
    return False


def _is_persistence_go_path(rel: str) -> bool:
    return (
        "/infrastructure/" in rel
        or "/persistence/" in rel
        or "/runtime/search/es/" in rel
    )


def _is_mongo_seed_scenario(rel: str) -> bool:
    # 仅 _id 的 Mongo seed 可保留；双键由 T7 另拦
    return "/scenarios/" in rel and rel.endswith(".json")


def _is_test_path(rel: str) -> bool:
    return (
        "/test/" in rel
        or "/tests/" in rel
        or rel.endswith("_test.go")
        or rel.endswith("_test.dart")
        or rel.endswith("_test.py")
        or "__local_contract_test" in rel
        or "__api_integration_test" in rel
    )


def _is_governance_scanner(rel: str) -> bool:
    """Separate policy implementation from runtime contract sources."""
    path = Path(rel)
    return (
        rel.startswith("quwoquan_ops/gate/")
        or "/scripts/verify/" in rel
        or (
            "/scripts/runtime/" in rel
            and path.name.startswith("verify_")
        )
    )


def _is_governance_test(rel: str) -> bool:
    return _is_test_path(rel) and "single_track_contracts" in Path(rel).name


def _is_rejection_context(lines: list[str], line_number: int) -> bool:
    start = max(0, line_number - 12)
    end = min(len(lines), line_number + 12)
    context = "\n".join(lines[start:end])
    return bool(
        re.search(
            r"reject|拒绝|forbidden|不得|禁止|retired|退休|must not|must be rejected|"
            r"invalid|bad request|unknown field|fails closed|"
            r"not in |isdisjoint|does not contain|must not contain|never accepts",
            context,
            re.I,
        )
    )


def _json_object_has_dual_id(obj: object) -> bool:
    if isinstance(obj, dict):
        if "_id" in obj and "id" in obj:
            return True
        return any(_json_object_has_dual_id(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_json_object_has_dual_id(v) for v in obj)
    return False


def scan_file(path: Path, inv: Inventory) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    rel = path.relative_to(ROOT).as_posix()
    suffix = path.suffix
    if _is_governance_scanner(rel) or _is_governance_test(rel):
        return
    lines = text.splitlines()

    if is_metadata_object_yaml(path) and TOP_LEVEL_VERSION.search(text):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^version:\s*", line):
                inv.add("T1_metadata_top_level_version", path, f"L{lineno}: {line.strip()}")
                break

    if suffix in {".yaml", ".yml"}:
        in_metadata_contract = rel.startswith("quwoquan_service/contracts/metadata/")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if in_metadata_contract and (
                ALIASES_LINE.search(line) or re.search(r"^\s*-\s*aliases\s*:", line)
            ):
                inv.add("T2_metadata_aliases", path, f"L{lineno}: {line.strip()}")
            if in_metadata_contract and SKIP_EMPTY_ALIASES.search(line):
                inv.add("T2_skip_empty_string_aliases", path, f"L{lineno}: {line.strip()}")
            if in_metadata_contract and AUTH_REQUIRED_LINE.search(line):
                inv.add("T4_auth_required", path, f"L{lineno}: {line.strip()}")

    for field_name in FORBIDDEN_ENVELOPE_FIELDS:
        if field_name not in text:
            continue
        # 军规 / 规格中列举禁词（禁止 schemaVersion 等）不计违规
        if suffix in {".md", ".mdc"} and (
            "禁止" in text
            or "forbidden" in text.lower()
            or "retired" in text.lower()
            or "GATE_BLOCK" in text
        ):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if field_name not in line:
                continue
            if _is_comment_line(line, suffix):
                continue
            if _is_rejection_context(lines, lineno):
                continue
            if re.search(rf"\b{field_name}\b", line):
                inv.add("T1_forbidden_envelope_field", path, f"L{lineno}: {field_name}")

    for match in VERSIONED_INLINE.finditer(text):
        value = match.group(0)
        if "/posts/" in value or "posts/article" in value:
            continue
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add("T1_versioned_schema_identity", path, value)

    for match in SCHEMA_VALUE_V_SUFFIX.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add("T1_versioned_schema_identity", path, match.group(0))

    for match in NUMERIC_SCHEMA_LITERAL.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add("T1_numeric_schema_identity", path, match.group(0))

    if OPTIONAL_ALIAS_HELPER.search(text):
        inv.add("T3_alias_helper", path, "alias helper symbol")

    # 多键解码：Dart / Go 全量（含手写 lib / generated），同标识符且键名不同才计
    if suffix in {".dart", ".go"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            for match in MULTI_KEY_DECODE.finditer(line):
                if match.group("k1") == match.group("k2"):
                    continue
                inv.add(
                    "T3_multi_key_decode",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )
            if MULTI_KEY_GO_TEMPLATE.search(line):
                inv.add(
                    "T3_multi_key_decode",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )

    # specs / 军规：禁止再教短期双读或协议版本身份（同行含「禁止」则放过）
    if suffix in {".md", ".mdc"} and (
        rel.startswith("specs/") or rel.startswith(".cursor/rules/")
    ):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not DOC_DUAL_TRACK_TEACHING.search(line):
                continue
            if re.search(r"禁止|不得|GATE_BLOCK|已删除|不得保留", line):
                continue
            inv.add(
                "T5_doc_dual_track_teaching",
                path,
                f"L{lineno}: {line.strip()[:140]}",
            )

    if suffix == ".dart" and (
        "mapListFirstPresent" in text or "mapListFirstNonEmpty" in text
    ):
        if "/lib/" in rel.replace("\\", "/"):
            inv.add(
                "T3_map_list_first_present",
                path,
                "mapListFirstPresent/mapListFirstNonEmpty forbidden in lib",
            )
        else:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "mapListFirstPresent" in line or "mapListFirstNonEmpty" in line:
                    window = "\n".join(text.splitlines()[lineno - 1 : lineno + 6])
                    keys = re.findall(r"'([A-Za-z0-9_]+)'", window)
                    if len(keys) >= 2:
                        inv.add(
                            "T3_map_list_first_present",
                            path,
                            f"L{lineno}: multi-key {keys}",
                        )

    for pattern in COMPAT_SMELLS:
        for lineno, line in enumerate(lines, start=1):
            if _is_comment_line(line, suffix):
                continue
            if not pattern.search(line):
                continue
            if _is_rejection_context(lines, lineno):
                continue
            # 军规/规格中「禁止 dual-read / 逃逸」等否定句不计为气味
            if re.search(
                r"禁止|不得|不保留|无\s*dual|删除|GATE_BLOCK|must not|forbidden|逃逸|阻断",
                line,
                re.I,
            ):
                continue
            if rel.startswith(".cursor/rules/") or rel.startswith("specs/"):
                # 规则清单里出现 mode=compat 等禁词本身即治理文案
                continue
            inv.add("T4_compat_smell", path, f"L{lineno}: {line.strip()[:120]}")

    # 正向 alias 测试语义
    if "test" in rel and suffix in {".dart", ".go", ".py"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if POSITIVE_ALIAS_TEST.search(line):
                # 同行若已含 rejects/拒绝 则放过
                if re.search(r"reject|拒绝|forbidden|不得|must not", line, re.I):
                    continue
                inv.add(
                    "T6_positive_alias_test",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )

    # T3_wire_id_key：客户端 wire 禁止 _id JSON 键
    if suffix == ".dart" and (
        "/lib/" in rel
        or "/packages/" in rel
        or "/generated/" in rel
        or _is_test_path(rel)
    ):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            if not DART_WIRE_ID_KEY.search(line) and "['_id']" not in line and '["_id"]' not in line:
                continue
            if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                continue
            # 测试夹具里用 _id 证明拒绝
            if _is_test_path(rel) and (
                "拒绝 _id" in text
                or "rejects _id" in text
                or "reject _id" in text.lower()
                or "rejects aggregate storage" in text
            ):
                if re.search(
                    r"""['\"]_id['\"]\s*:|\[['\"]_id['\"]\]\s*=""",
                    line,
                ):
                    continue
            inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

    if suffix == ".go" and not _is_persistence_go_path(rel):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            if GO_BSON_ID_TAG.search(line) and not GO_JSON_ID_TAG.search(line):
                continue
            if GO_JSON_ID_TAG.search(line):
                if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                    continue
                inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")
                continue
            # map 出站 "_id":
            if GO_MAP_ID_KEY.search(line) and (
                "/adapters/" in rel
                or "/application/" in rel
                or "/domain/" in rel
                or "/generated/" in rel
            ):
                if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                    continue
                inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

    # T3_multi_key_helper：_firstNonEmpty(..., '_id', ...)
    if suffix in {".dart", ".go"} and MULTI_KEY_HELPER_ID.search(text):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "_firstNonEmpty" in line or "mapListFirstPresent" in line or "mapListFirstNonEmpty" in line:
                if "'_id'" in line or '"_id"' in line:
                    inv.add(
                        "T3_multi_key_helper",
                        path,
                        f"L{lineno}: {line.strip()[:140]}",
                    )

    # T5：metadata 正向 _id/id 兼容教学
    if rel.startswith("quwoquan_service/contracts/metadata/") and suffix in {
        ".yaml",
        ".yml",
        ".md",
    }:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not ID_COMPAT_TEACHING.search(line):
                continue
            if re.search(r"禁止|不得|reject|拒绝|GATE_BLOCK", line, re.I):
                continue
            # source: _id 存储投影合法，不在此拦
            if re.search(r"^\s*source:\s*_id\s*$", line):
                continue
            inv.add(
                "T5_id_compat_teaching",
                path,
                f"L{lineno}: {line.strip()[:140]}",
            )

    # T7：fixture 同对象同时含 _id 与 id
    if suffix == ".json" and (
        "/test_fixtures/" in rel
        or "/fixtures/" in rel
        or (rel.startswith("quwoquan_app/assets/") and "fixture" in rel.lower())
        or _is_mongo_seed_scenario(rel)
    ):
        # scenarios 仅当双键并存才拦（纯 Mongo seed 只有 _id 放过）
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None and _json_object_has_dual_id(data):
            inv.add(
                "T7_fixture_dual_id",
                path,
                "JSON object contains both _id and id keys",
            )


def write_inventory(inv: Inventory, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Single-track contract inventory",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(inv.counts):
        lines.append(f"- {key}: {inv.counts[key]}")
    lines.extend(["", "## Findings", ""])
    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for finding in inv.findings:
        by_cat[finding.category].append(finding)
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for item in by_cat[cat][:200]:
            lines.append(f"- `{item.path}`: {item.detail}")
        if len(by_cat[cat]) > 200:
            lines.append(f"- ... {len(by_cat[cat]) - 200} more")
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "counts": dict(inv.counts),
        "total": sum(inv.counts.values()),
    }
    summary_path = out_path.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory-out",
        default=str(
            ROOT / ".qwq_output/env/repo/runs/single-track-inventory.md"
        ),
    )
    args = parser.parse_args()

    inv = Inventory()
    for path in iter_files():
        scan_file(path, inv)

    out_path = Path(args.inventory_out)
    write_inventory(inv, out_path)

    total = sum(inv.counts.values())
    print(
        f"[single-track] inventory={out_path.relative_to(ROOT).as_posix()} "
        f"total_findings={total}"
    )
    for key in sorted(inv.counts):
        print(f"  {key}: {inv.counts[key]}")

    if total == 0:
        print("[single-track] OK: zero dual-track / versioned-contract findings")
        return 0

    print("[single-track] FAIL: dual-track or versioned-contract residue remains", file=sys.stderr)
    for finding in inv.findings[:40]:
        print(f"  {finding.category}: {finding.path}: {finding.detail}", file=sys.stderr)
    if total > 40:
        print(f"  ... {total - 40} more (see inventory)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

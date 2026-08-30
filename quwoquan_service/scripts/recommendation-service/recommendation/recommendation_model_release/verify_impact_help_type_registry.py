#!/usr/bin/env python3
"""影响力 helpType 注册表单一真相源门禁（§23 去桥接闭集校验，对齐交集 verify）。

唯一真相源:
  services/recommendation-service/contracts/recommendation/recommendation_model_release/impact_help_type_registry.yaml

校验项:
  1. 注册表自洽：helpTypes 闭集非空、每项 iconKey/summaryAction/evidenceAction 完整；
     iconKey ∈ toneByIconKey；toneByIconKey 值 ∈ toneLegend；defaults 完整且 iconKey/tone 在闭集内。
  2. 云侧 Go codegen 产物 runtime/impact/help_type_table.go 与注册表逐字段一致（取代散落手写常量/switch）：
     HelpTypes / IconKeyByHelpType / SummaryActionByHelpType / EvidenceActionByHelpType /
     BehaviorActionToHelpType / DefaultIconKey / DefaultSummaryAction / DefaultEvidenceAction == registry。
  3. 端侧 Dart codegen 产物 impact_help_type_metadata.g.dart 与注册表一致：
     impactHelpTypeKeys / impactIconKeyByHelpType / impactToneByIconKey / impactDefaultTone / impactDefaultIconKey。
  4. 端 IntersectionIconResolver 已查 impactToneByIconKey，不得回归硬编码 impact 色调 switch；
     _iconByKey 的真实字符串键覆盖注册表全部 impact iconKey（含 cascadePath 兜底），
     且不得回归 legacy 别名 compass/read。
  5. 云侧消费方已查 rtimpact.* 表，不得回归手写 helpType switch / 重复常量 / 字面量：
     author_impact_language.go / author_impact_evidence_view.go / behavior_service.go / circle_service.go /
     author_impact_store.go（已删 AuthorImpactHelp* 重复常量）。
  6. fixtures 无 legacy impact iconKey 漂移（audience / compass / read）。

退出码: 0 通过 / 1 失败。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
SVC = REPO_ROOT / "quwoquan_service"
REGISTRY = SVC / "services/recommendation-service/contracts/recommendation/recommendation_model_release/impact_help_type_registry.yaml"
GO_TABLE = SVC / "runtime/impact/help_type_table.go"
DART_META = (
    REPO_ROOT
    / "quwoquan_app/lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/impact_help_type_metadata.g.dart"
)
RESOLVER = (
    REPO_ROOT
    / "quwoquan_app/lib/service/recommendation_service/recommendation"
    / "recommendation_feature_profile_view/presentation/intersection_icon_resolver.dart"
)

LANG_GO = SVC / "services/content-service/internal/content/post/application/authorimpact/author_impact_language.go"
EVIDENCE_GO = SVC / "services/content-service/internal/content/post/application/authorimpact/author_impact_evidence_view.go"
BEHAVIOR_GO = (
    SVC
    / "services/content-service/internal/content/content_behavior_fact/application/behavior_service.go"
)
#: `rm_author_impact` 的持久化已由 recommendation-service 接管，content-service
#: 只经 author_impact_reader_client 读取，author_impact_store.go 随之退役。去重
#: 不变量不随该文件消失：整棵 content-service 实现树都不得再定义第二份
#: AuthorImpactHelp* 常量。
CONTENT_SERVICE_INTERNAL = SVC / "services/content-service/internal"
CIRCLE_GO = SVC / "services/circle-service/internal/circle_management/circle/application/circle_service.go"

FIXTURE_DIR = SVC / "services/content-service/tests/support/contract_fixtures/scenarios"

LEGACY_ICON_KEYS = {"audience", "compass", "read"}


def fail(msg: str) -> None:
    print(f"[verify-impact-help-type-registry] FAIL: {msg}")
    sys.exit(1)


# ── registry ───────────────────────────────────────────────────────────────
def load_registry() -> dict:
    if not REGISTRY.exists():
        fail(f"missing registry: {REGISTRY}")
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    tone_legend = data.get("toneLegend")
    tone_by_icon = data.get("toneByIconKey")
    help_types = data.get("helpTypes")
    defaults = data.get("defaults")
    if not isinstance(tone_legend, list) or not tone_legend:
        fail("toneLegend must be a non-empty list")
    if not isinstance(tone_by_icon, dict) or not tone_by_icon:
        fail("toneByIconKey must be a non-empty mapping")
    if not isinstance(help_types, list) or not help_types:
        fail("helpTypes must be a non-empty list")
    if not isinstance(defaults, dict) or not defaults:
        fail("defaults must be a non-empty mapping")

    tone_set = set(tone_legend)
    for icon, tone in tone_by_icon.items():
        if tone not in tone_set:
            fail(f"toneByIconKey[{icon!r}] tone {tone!r} not in toneLegend")

    seen: set[str] = set()
    for h in help_types:
        ht = h.get("helpType")
        if not ht:
            fail("helpType entry missing helpType")
        if ht in seen:
            fail(f"duplicate helpType {ht}")
        seen.add(ht)
        if not str(h.get("iconKey", "")).strip():
            fail(f"helpType {ht} missing iconKey")
        if h["iconKey"] not in tone_by_icon:
            fail(f"helpType {ht} iconKey {h['iconKey']!r} not in toneByIconKey closed set")
        for act in ("summaryAction", "evidenceAction"):
            a = h.get(act)
            if not isinstance(a, dict) or not str(a.get("key", "")).strip() or not str(a.get("label", "")).strip():
                fail(f"helpType {ht} {act} must have key+label")
        if not isinstance(h.get("behaviorActions", []), list):
            fail(f"helpType {ht} behaviorActions must be a list")

    if not str(defaults.get("iconKey", "")).strip():
        fail("defaults.iconKey is empty")
    if defaults["iconKey"] not in tone_by_icon:
        fail(f"defaults.iconKey {defaults['iconKey']!r} not in toneByIconKey closed set")
    if defaults.get("tone") not in tone_set:
        fail(f"defaults.tone {defaults.get('tone')!r} not in toneLegend")
    for act in ("summaryAction", "evidenceAction"):
        a = defaults.get(act)
        if not isinstance(a, dict) or not str(a.get("key", "")).strip() or not str(a.get("label", "")).strip():
            fail(f"defaults.{act} must have key+label")
    return data


def registry_expected(data: dict) -> dict:
    helps = data["helpTypes"]
    behavior_to_help: dict[str, str] = {}
    for h in helps:
        for action in h.get("behaviorActions") or []:
            if action in behavior_to_help:
                fail(f"behaviorAction {action!r} mapped to multiple helpTypes")
            behavior_to_help[action] = h["helpType"]
    return {
        "helpTypes": [h["helpType"] for h in helps],
        "iconKeyByHelpType": {h["helpType"]: h["iconKey"] for h in helps},
        "toneByIconKey": dict(data["toneByIconKey"]),
        "summaryActionByHelpType": {h["helpType"]: (h["summaryAction"]["key"], h["summaryAction"]["label"]) for h in helps},
        "evidenceActionByHelpType": {h["helpType"]: (h["evidenceAction"]["key"], h["evidenceAction"]["label"]) for h in helps},
        "behaviorActionToHelpType": behavior_to_help,
        "defaultIconKey": data["defaults"]["iconKey"],
        "defaultTone": data["defaults"]["tone"],
        "defaultSummaryAction": (data["defaults"]["summaryAction"]["key"], data["defaults"]["summaryAction"]["label"]),
        "defaultEvidenceAction": (data["defaults"]["evidenceAction"]["key"], data["defaults"]["evidenceAction"]["label"]),
    }


# ── Go table ─────────────────────────────────────────────────────────────────
def _go_block(src: str, header: str) -> str:
    pat = rf"{re.escape(header)}\{{(.*?)\n\}}"
    m = re.search(pat, src, re.S)
    if not m:
        fail(f"Go table missing block: {header}")
    return m.group(1)


def parse_go_table() -> dict:
    if not GO_TABLE.exists():
        fail(f"missing Go table: {GO_TABLE} (run `make codegen-impact`)")
    src = GO_TABLE.read_text(encoding="utf-8")

    # const HelpXxx = "value" → const-name → helpType value
    const_to_help: dict[str, str] = {}
    for name, val in re.findall(r'(Help[A-Za-z]+)\s*=\s*"([^"]+)"', src):
        const_to_help[name] = val
    if not const_to_help:
        fail("Go table has no Help* const definitions")

    def resolve_const(token: str) -> str:
        token = token.strip()
        if token.startswith('"') and token.endswith('"'):
            return token[1:-1]
        if token in const_to_help:
            return const_to_help[token]
        fail(f"Go table unresolved const token {token!r}")

    # HelpTypes []string{...}
    help_types_block = _go_block(src, "var HelpTypes = []string")
    help_types = [resolve_const(t) for t in re.findall(r"(Help[A-Za-z]+|\"[^\"]+\")", help_types_block)]

    # IconKeyByHelpType map[string]string{ HelpXxx: "icon", }
    icon_block = _go_block(src, "var IconKeyByHelpType = map[string]string")
    icon_by_help = {
        resolve_const(k): v
        for k, v in re.findall(r"(Help[A-Za-z]+|\"[^\"]+\")\s*:\s*\"([^\"]*)\"", icon_block)
    }

    def parse_action_map(header: str) -> dict[str, tuple[str, str]]:
        block = _go_block(src, header)
        out: dict[str, tuple[str, str]] = {}
        for k, key, label in re.findall(
            r"(Help[A-Za-z]+|\"[^\"]+\")\s*:\s*\{Key:\s*\"([^\"]*)\",\s*Label:\s*\"([^\"]*)\"\}",
            block,
        ):
            out[resolve_const(k)] = (key, label)
        return out

    summary = parse_action_map("var SummaryActionByHelpType = map[string]ImpactAction")
    evidence = parse_action_map("var EvidenceActionByHelpType = map[string]ImpactAction")

    # BehaviorActionToHelpType map[string]string{ "action": HelpXxx, }
    beh_block = _go_block(src, "var BehaviorActionToHelpType = map[string]string")
    behavior_to_help = {
        k: resolve_const(v)
        for k, v in re.findall(r"\"([^\"]+)\"\s*:\s*(Help[A-Za-z]+|\"[^\"]+\")", beh_block)
    }

    default_icon = _scalar_const(src, "DefaultIconKey")
    default_summary = _action_const(src, "DefaultSummaryAction")
    default_evidence = _action_const(src, "DefaultEvidenceAction")

    return {
        "helpTypes": help_types,
        "iconKeyByHelpType": icon_by_help,
        "summaryActionByHelpType": summary,
        "evidenceActionByHelpType": evidence,
        "behaviorActionToHelpType": behavior_to_help,
        "defaultIconKey": default_icon,
        "defaultSummaryAction": default_summary,
        "defaultEvidenceAction": default_evidence,
    }


def _scalar_const(src: str, name: str) -> str:
    m = re.search(rf'{re.escape(name)}\s*=\s*"([^"]*)"', src)
    if not m:
        fail(f"Go table missing const {name}")
    return m.group(1)


def _action_const(src: str, name: str) -> tuple[str, str]:
    m = re.search(rf'{re.escape(name)}\s*=\s*ImpactAction\{{Key:\s*"([^"]*)",\s*Label:\s*"([^"]*)"\}}', src)
    if not m:
        fail(f"Go table missing ImpactAction const {name}")
    return m.group(1), m.group(2)


# ── Dart metadata ────────────────────────────────────────────────────────────
def parse_dart_meta() -> dict:
    if not DART_META.exists():
        fail(f"missing Dart metadata: {DART_META} (run `make codegen-app`)")
    src = DART_META.read_text(encoding="utf-8")

    keys_m = re.search(r"impactHelpTypeKeys\s*=\s*<String>\[(.*?)\];", src, re.S)
    if not keys_m:
        fail("Dart metadata missing impactHelpTypeKeys")
    help_keys = re.findall(r"[\"']([^\"']+)[\"']", keys_m.group(1))

    def parse_map(name: str) -> dict[str, str]:
        m = re.search(rf"{name}\s*=\s*<String, String>\{{(.*?)\}};", src, re.S)
        if not m:
            fail(f"Dart metadata missing {name}")
        return {
            k: v
            for k, v in re.findall(r"[\"']([^\"']+)[\"']\s*:\s*[\"']([^\"']+)[\"']", m.group(1))
        }

    icon_by_help = parse_map("impactIconKeyByHelpType")
    tone_by_icon = parse_map("impactToneByIconKey")
    default_tone = re.search(r"impactDefaultTone\s*=\s*[\"']([^\"']+)[\"']", src)
    default_icon = re.search(r"impactDefaultIconKey\s*=\s*[\"']([^\"']+)[\"']", src)
    if not default_tone or not default_icon:
        fail("Dart metadata missing impactDefaultTone / impactDefaultIconKey")
    return {
        "helpTypes": help_keys,
        "iconKeyByHelpType": icon_by_help,
        "toneByIconKey": tone_by_icon,
        "defaultTone": default_tone.group(1),
        "defaultIconKey": default_icon.group(1),
    }


# ── diff helpers ─────────────────────────────────────────────────────────────
def diff_map(name: str, expected: dict, actual: dict, problems: list[str]) -> None:
    for key in sorted(set(expected) | set(actual)):
        if key not in actual:
            problems.append(f"{name}: missing key '{key}' (registry={expected[key]!r})")
        elif key not in expected:
            problems.append(f"{name}: unregistered key '{key}'={actual[key]!r}")
        elif expected[key] != actual[key]:
            problems.append(f"{name}: key '{key}' drift registry={expected[key]!r} actual={actual[key]!r}")


def diff_list(name: str, expected: list, actual: list, problems: list[str]) -> None:
    if expected != actual:
        problems.append(f"{name}: list drift registry={expected!r} actual={actual!r}")


# ── consumer anti-regression ─────────────────────────────────────────────────
def check_consumers(exp: dict, problems: list[str]) -> None:
    checks = [
        (LANG_GO, ["rtimpact.IconKeyByHelpType", "rtimpact.SummaryActionByHelpType"], "author_impact_language.go"),
        (EVIDENCE_GO, ["rtimpact.EvidenceActionByHelpType"], "author_impact_evidence_view.go"),
        (BEHAVIOR_GO, ["rtimpact.BehaviorActionToHelpType"], "behavior_service.go"),
    ]
    for path, tokens, where in checks:
        if not path.exists():
            problems.append(f"{where} missing: {path}")
            continue
        src = path.read_text(encoding="utf-8")
        for tok in tokens:
            if tok not in src:
                problems.append(f"consumer not table-driven: {where} must consume {tok}")

    # content-service 实现树内不得出现第二份 AuthorImpactHelp* 常量定义（dedup）。
    if not CONTENT_SERVICE_INTERNAL.is_dir():
        problems.append(
            f"content-service implementation tree missing: {CONTENT_SERVICE_INTERNAL}"
        )
    else:
        scanned = 0
        for path in sorted(CONTENT_SERVICE_INTERNAL.rglob("*.go")):
            scanned += 1
            if re.search(r"AuthorImpactHelp[A-Za-z]+\s*=", path.read_text(encoding="utf-8")):
                problems.append(
                    f"{path.relative_to(REPO_ROOT)} must not redefine AuthorImpactHelp* "
                    "constants (use rtimpact.Help*)"
                )
        if scanned == 0:
            problems.append(
                f"AuthorImpactHelp* dedup scan found no Go source under "
                f"{CONTENT_SERVICE_INTERNAL}; 目录轴变更后必须把扫描面指向新的 canonical 路径"
            )

    # circle_service.go must reference rtimpact.Help* (not helpType string literals).
    if CIRCLE_GO.exists():
        circle = CIRCLE_GO.read_text(encoding="utf-8")
        if not re.search(r"\brtimpact\.Help[A-Z][A-Za-z0-9_]*\b", circle):
            problems.append("circle_service.go must use rtimpact.Help* for helpType (no string literals)")
        if re.search(r'"helpType"\s*:\s*"(relationship|community|spread|decision|knowledge|audience)"', circle):
            problems.append("circle_service.go still has hardcoded helpType string literal")
    else:
        problems.append(f"circle_service.go missing: {CIRCLE_GO}")


def _strip_dart_comments(src: str) -> str:
    """移除 Dart 注释，同时保留字符串中的注释标记与源码行结构。"""

    out: list[str] = []
    index = 0
    length = len(src)
    while index < length:
        if src.startswith("//", index):
            newline = src.find("\n", index + 2)
            if newline < 0:
                out.append(" " * (length - index))
                break
            out.append(" " * (newline - index))
            out.append("\n")
            index = newline + 1
            continue
        if src.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if src.startswith("/*", index):
                    depth += 1
                    index += 2
                elif src.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            comment = src[start:index]
            out.append("".join("\n" if char == "\n" else " " for char in comment))
            continue
        if src[index] in ("'", '"'):
            quote = src[index]
            delimiter = quote * 3 if src.startswith(quote * 3, index) else quote
            out.append(delimiter)
            index += len(delimiter)
            while index < length:
                if src.startswith(delimiter, index):
                    out.append(delimiter)
                    index += len(delimiter)
                    break
                char = src[index]
                out.append(char)
                index += 1
                if char == "\\" and index < length:
                    out.append(src[index])
                    index += 1
            continue
        out.append(src[index])
        index += 1
    return "".join(out)


def _matching_curly(src: str, opening: int) -> int | None:
    depth = 0
    index = opening
    while index < len(src):
        char = src[index]
        if char in ("'", '"'):
            delimiter = char * 3 if src.startswith(char * 3, index) else char
            index += len(delimiter)
            while index < len(src):
                if src.startswith(delimiter, index):
                    index += len(delimiter)
                    break
                if src[index] == "\\":
                    index += 2
                else:
                    index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _top_level_map_entries(body: str) -> list[str]:
    entries: list[str] = []
    start = 0
    stack: list[str] = []
    closing = {"(": ")", "[": "]", "{": "}"}
    index = 0
    while index < len(body):
        char = body[index]
        if char in ("'", '"'):
            delimiter = char * 3 if body.startswith(char * 3, index) else char
            index += len(delimiter)
            while index < len(body):
                if body.startswith(delimiter, index):
                    index += len(delimiter)
                    break
                if body[index] == "\\":
                    index += 2
                else:
                    index += 1
            continue
        if char in closing:
            stack.append(closing[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char == "," and not stack:
            entries.append(body[start:index])
            start = index + 1
        index += 1
    entries.append(body[start:])
    return entries


def _parse_icon_map_keys(src: str, problems: list[str]) -> tuple[str, set[str]]:
    cleaned = _strip_dart_comments(src)
    declaration = re.compile(
        r"\bstatic\s+const\s+Map\s*<\s*String\s*,\s*IconData\s*>\s*"
        r"_iconByKey\s*=\s*<\s*String\s*,\s*IconData\s*>\s*\{"
    )
    matches = list(declaration.finditer(cleaned))
    if len(matches) != 1:
        problems.append(
            "resolver must declare exactly one static const Map<String, IconData> "
            "_iconByKey with literal glyph entries"
        )
        return cleaned, set()

    opening = matches[0].end() - 1
    closing = _matching_curly(cleaned, opening)
    if closing is None:
        problems.append("resolver _iconByKey map has no matching closing brace")
        return cleaned, set()

    keys: set[str] = set()
    key_pattern = re.compile(
        r'^\s*(?:\'([A-Za-z][A-Za-z0-9]*)\'|"([A-Za-z][A-Za-z0-9]*)")\s*:'
    )
    for raw_entry in _top_level_map_entries(cleaned[opening + 1 : closing]):
        entry = raw_entry.strip()
        if not entry:
            continue
        key_match = key_pattern.match(entry)
        if key_match is None:
            problems.append(
                "resolver _iconByKey must use only literal string keys and explicit glyph values"
            )
            continue
        key = key_match.group(1) or key_match.group(2)
        if key in keys:
            problems.append(f"resolver _iconByKey duplicates glyph key '{key}'")
        keys.add(key)
    return cleaned, keys


def validate_resolver_source(src: str, exp: dict, problems: list[str]) -> None:
    cleaned, mapped_keys = _parse_icon_map_keys(src, problems)
    if not re.search(r"\bimpactToneByIconKey\s*\[", cleaned):
        problems.append("resolver must consume impactToneByIconKey (no hardcoded impact tone switch)")

    # anti-regression: no legacy aliases in the canonical map or old switch cases.
    for legacy in ("compass", "read"):
        if legacy in mapped_keys:
            problems.append(
                f"resolver re-introduced legacy iconKey map key '{legacy}' "
                "(zero-compat: removed)"
            )
        if re.search(rf"\bcase\s+(['\"]){re.escape(legacy)}\1\s*:", cleaned):
            problems.append(
                f"resolver re-introduced legacy iconKey switch case '{legacy}' "
                "(zero-compat: removed)"
            )

    # The map itself must cover the registry closed set plus the default cascade.
    needed = set(exp["iconKeyByHelpType"].values()) | {exp["defaultIconKey"]}
    for icon in sorted(needed - mapped_keys):
        problems.append(
            f"resolver _iconByKey missing glyph map entry for impact iconKey '{icon}'"
        )


def check_resolver(exp: dict, problems: list[str]) -> None:
    if not RESOLVER.exists():
        problems.append(f"resolver missing: {RESOLVER}")
        return
    validate_resolver_source(RESOLVER.read_text(encoding="utf-8"), exp, problems)


def check_fixtures(problems: list[str]) -> None:
    if not FIXTURE_DIR.exists():
        return
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for legacy in LEGACY_ICON_KEYS:
            if re.search(rf'"iconKey"\s*:\s*"{legacy}"', text):
                problems.append(f"fixture {path.name} has legacy impact iconKey '{legacy}' (use registry standard key)")


def main() -> int:
    data = load_registry()
    exp = registry_expected(data)
    go = parse_go_table()
    dart = parse_dart_meta()

    problems: list[str] = []

    # registry ↔ Go
    diff_list("Go.HelpTypes", exp["helpTypes"], go["helpTypes"], problems)
    diff_map("Go.IconKeyByHelpType", exp["iconKeyByHelpType"], go["iconKeyByHelpType"], problems)
    diff_map("Go.SummaryActionByHelpType", exp["summaryActionByHelpType"], go["summaryActionByHelpType"], problems)
    diff_map("Go.EvidenceActionByHelpType", exp["evidenceActionByHelpType"], go["evidenceActionByHelpType"], problems)
    diff_map("Go.BehaviorActionToHelpType", exp["behaviorActionToHelpType"], go["behaviorActionToHelpType"], problems)
    if exp["defaultIconKey"] != go["defaultIconKey"]:
        problems.append(f"Go.DefaultIconKey drift registry={exp['defaultIconKey']!r} go={go['defaultIconKey']!r}")
    if exp["defaultSummaryAction"] != go["defaultSummaryAction"]:
        problems.append(f"Go.DefaultSummaryAction drift registry={exp['defaultSummaryAction']!r} go={go['defaultSummaryAction']!r}")
    if exp["defaultEvidenceAction"] != go["defaultEvidenceAction"]:
        problems.append(f"Go.DefaultEvidenceAction drift registry={exp['defaultEvidenceAction']!r} go={go['defaultEvidenceAction']!r}")

    # registry ↔ Dart
    diff_list("Dart.impactHelpTypeKeys", exp["helpTypes"], dart["helpTypes"], problems)
    diff_map("Dart.impactIconKeyByHelpType", exp["iconKeyByHelpType"], dart["iconKeyByHelpType"], problems)
    diff_map("Dart.impactToneByIconKey", exp["toneByIconKey"], dart["toneByIconKey"], problems)
    if exp["defaultTone"] != dart["defaultTone"]:
        problems.append(f"Dart.impactDefaultTone drift registry={exp['defaultTone']!r} dart={dart['defaultTone']!r}")
    if exp["defaultIconKey"] != dart["defaultIconKey"]:
        problems.append(f"Dart.impactDefaultIconKey drift registry={exp['defaultIconKey']!r} dart={dart['defaultIconKey']!r}")

    check_resolver(exp, problems)
    check_consumers(exp, problems)
    check_fixtures(problems)

    if problems:
        for p in problems:
            print(f"[verify-impact-help-type-registry] FAIL: {p}")
        return 1

    print(
        f"[verify-impact-help-type-registry] OK: {len(exp['helpTypes'])} helpTypes registered; "
        f"Go table + Dart metadata + resolver + consumers + fixtures aligned "
        f"(single source = impact_help_type_registry.yaml)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

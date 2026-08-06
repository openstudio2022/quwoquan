#!/usr/bin/env python3
"""端侧对象化架构门禁 v1（ratchet 基线），云侧 `verify_service_architecture.py` 的对等物。

目标形态（与云侧 DDD 同构，层名等价见
`object_path_map.APP_TO_CLOUD_LAYER_EQUIVALENCE`）：

    quwoquan_app/lib/
    ├─ <domain>/<context>/<object>/{domain,application,adapters,presentation}/
    ├─ runtime/        # 唯一公共 runtime 横切面（transport/codec/errors/config/auth/
    │                  # di/observability/platform/shell）
    ├─ design_system/  # 唯一设计系统横切面
    └─ l10n/           # flutter gen-l10n 的 arb 根，取自 quwoquan_app/l10n.yaml

v1 校验三条规则：

R1 `app_lib_top_level`
    `lib/` 顶层只允许：`<domain>/`（ContractGraph roster 派生）、`runtime/`、
    `design_system/`、l10n 根，以及入口文件 `main*.dart`。

R2 `cross_cutting_target_reverse_import`
    横切面禁止依赖业务对象。目标形态目前几乎不存在（`lib/runtime/`、
    `lib/design_system/` 尚未建立），因此该规则在**目标空间**求值：文件的归属由
    `object_path_map.py` 派生，凡派生归属为横切面的文件，禁止 import 派生归属为
    某个 domain 的文件。这样在物理搬迁（W2/W3）之前就能测出真实的反向依赖量，
    并随搬迁与解耦单调收敛。

R3 `cross_cutting_physical_reverse_import`
    同一方向性约束在**物理空间**的完整表达：物理位于 `lib/runtime/**` 或
    `lib/design_system/**` 的文件，禁止 import 物理位于 `lib/<domain>/**` 的文件。
    这是搬迁完成后的终态断言；横切面目录建立前它恒为空集。

组合根例外（与云侧 `cmd/` 同义，不是逃逸）：`runtime/di/**` 与顶层入口
`main*.dart` 是装配点，其职责就是把各 domain 的实现接线到一起，因此不纳入 R2/R3
的横切面禁令范围。除此之外没有任何豁免。

对象归属一律经 `quwoquan_ops/gate/object_path_map.py` 派生，本门禁不实现第二套
路径反推规则。复用的规则表达：`ObjectRoster`、`CONTRACT_GRAPH_PATH`、
`load_page_claims`、`scan_app`、`APP_ROOT`、`APP_LIB_ROOT`、`APP_SOURCE_SUFFIX`、
`APP_CROSS_CUTTING_ROOTS`。

ratchet 语义（沿用 `quwoquan_app/scripts/runtime/verify_lib_dart_io_budget.py`）：
当前违规全部写入基线 `quwoquan_ops/policies/gates/app_architecture_baseline.json`，
门禁只断言「违规只减不增」。基线外的新违规与基线中已消失的陈旧条目都会 BLOCK；
陈旧条目必须通过 `--write-baseline` 显式收敛，禁止长期挂账。

用法
----
    python3 quwoquan_ops/gate/verify_app_architecture.py
    python3 quwoquan_ops/gate/verify_app_architecture.py --domain content
    python3 quwoquan_ops/gate/verify_app_architecture.py --write-baseline
    python3 quwoquan_ops/gate/verify_app_architecture.py --domain content --write-baseline

`--domain <domain>` 供 16 条 domain 并行流使用：只比对该 domain 名下的 R2/R3 违规，
R1 是共享的顶层规则，任何 scope 都全量求值。`--write-baseline` 搭配 `--domain` 时
只重写该 domain 的基线分区，避免 16 条流互相覆盖。
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Sequence

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm  # noqa: E402

RULE_ID = "app-architecture/v1"

BASELINE_PATH = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "app_architecture_baseline.json"
)
L10N_CONFIG_PATH = ROOT / opm.APP_ROOT / "l10n.yaml"

RULE_TOP_LEVEL = "app_lib_top_level"
RULE_TARGET_REVERSE_IMPORT = "cross_cutting_target_reverse_import"
RULE_PHYSICAL_REVERSE_IMPORT = "cross_cutting_physical_reverse_import"

#: R1 是共享规则（顶层只有一份），R2/R3 按被依赖的 domain 归属到并行流。
SHARED_RULES = (RULE_TOP_LEVEL,)
DOMAIN_RULES = (RULE_TARGET_REVERSE_IMPORT, RULE_PHYSICAL_REVERSE_IMPORT)

#: 顶层唯一允许的文件形态：Flutter 入口。`app_bootstrap.dart` 与 shell 文件属于
#: `runtime/shell/`，不是入口，因此不在此列。
TOP_LEVEL_ENTRY_RE = re.compile(r"^main[a-z0-9_]*\.dart$")

#: 组合根：只有它可以同时依赖多个 domain（云侧 `cmd/` 的端侧对等物）。
COMPOSITION_ROOT_TARGET_PREFIXES = ("runtime/di/",)

IMPORT_RE = re.compile(r"""(?m)^\s*(?:import|export)\s+['"]([^'"]+)['"]""")
PACKAGE_URI_PREFIX = "package:quwoquan_app/"

LIB_PREFIX = f"{opm.APP_LIB_ROOT.as_posix()}/"


# ---------------------------------------------------------------------------
# 真相源载入
# ---------------------------------------------------------------------------


def load_roster() -> opm.ObjectRoster:
    """载入 ContractGraph 对象 roster；domain 集合即顶层白名单的业务部分。"""
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


def l10n_top_level_segment() -> str:
    """从 `quwoquan_app/l10n.yaml` 的 `arb-dir` 派生 l10n 顶层段，不另写死常量。"""
    document = yaml.safe_load(L10N_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    arb_dir = str(document.get("arb-dir") or "").strip().strip("/")
    if not arb_dir.startswith("lib/"):
        raise ValueError(
            f"{L10N_CONFIG_PATH}: arb-dir 必须位于 lib/ 之下，实测 {arb_dir!r}"
        )
    return arb_dir[len("lib/") :].split("/")[0]


def allowed_top_level_directories(roster: opm.ObjectRoster) -> set[str]:
    """`lib/` 顶层允许的目录：domain + 两个横切根 + l10n 根。"""
    return set(roster.domains) | set(opm.APP_CROSS_CUTTING_ROOTS) | {
        l10n_top_level_segment()
    }


# ---------------------------------------------------------------------------
# R1：顶层白名单
# ---------------------------------------------------------------------------


def scan_top_level_violations(roster: opm.ObjectRoster) -> list[str]:
    """返回 `lib/` 顶层不在白名单内的条目；目录以 `/` 结尾以示区分。"""
    allowed = allowed_top_level_directories(roster)
    violations: list[str] = []
    for entry in sorted((ROOT / opm.APP_LIB_ROOT).iterdir()):
        if entry.is_dir():
            if entry.name not in allowed:
                violations.append(f"{entry.name}/")
            continue
        if entry.suffix != opm.APP_SOURCE_SUFFIX or not TOP_LEVEL_ENTRY_RE.match(
            entry.name
        ):
            violations.append(entry.name)
    return sorted(violations)


# ---------------------------------------------------------------------------
# 归属派生（全部经 object_path_map，本文件不实现第二套反推规则）
# ---------------------------------------------------------------------------


def _lib_relative(repo_relative_path: str) -> str:
    return repo_relative_path[len(LIB_PREFIX) :]


def derive_target_root(row: dict, roster: opm.ObjectRoster) -> tuple[str, str | None]:
    """把 `object_path_map` 的一行归属折叠成目标树根。

    返回 ``("domain", <domain>)`` / ``("cross_cutting", "runtime"|"design_system")``
    / ``("unresolved", None)``。派生器判不出唯一对象但能判出唯一 domain 时
    （`context_only` / `domain_only` / 同 domain 内歧义），仍按该 domain 计；跨 domain
    的歧义一律 unresolved，绝不代替业务择一。
    """
    if row.get("objectId"):
        return "domain", row["domain"]

    object_ids = row.get("objectIds") or []
    if object_ids:
        domains = {roster.objects[object_id]["domain"] for object_id in object_ids}
        return ("domain", domains.pop()) if len(domains) == 1 else ("unresolved", None)

    context_ids = row.get("contextIds") or []
    if context_ids:
        domains = {context_id.split(".", 1)[0] for context_id in context_ids}
        return ("domain", domains.pop()) if len(domains) == 1 else ("unresolved", None)

    domains_claimed = row.get("domains") or []
    if len(domains_claimed) == 1 and domains_claimed[0] in roster.domains:
        return "domain", domains_claimed[0]

    cross_cutting_root = row.get("crossCuttingRoot")
    if cross_cutting_root:
        return "cross_cutting", cross_cutting_root
    return "unresolved", None


def is_composition_root(library_relative_path: str, target_path: str | None) -> bool:
    """组合根判定：顶层入口，或物理/派生目标落在 `lib/runtime/di/**`。

    物理路径与派生目标都要判：`object_path_map` 的横切目标路径构造只剥离现状
    `core/` 前缀，已经搬到 `lib/runtime/di/` 的文件会被再套一层 `runtime/`，
    单看派生目标会漏判已完成搬迁的组合根。
    """
    if TOP_LEVEL_ENTRY_RE.match(library_relative_path):
        return True
    if library_relative_path.startswith(COMPOSITION_ROOT_TARGET_PREFIXES):
        return True
    if not target_path or not target_path.startswith(LIB_PREFIX):
        return False
    return _lib_relative(target_path).startswith(COMPOSITION_ROOT_TARGET_PREFIXES)


class AppSourceIndex:
    """端侧 `lib/**` 生产文件的归属索引，唯一来源是 `object_path_map.scan_app`。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        page_claims, _ = opm.load_page_claims()
        rows, _ = opm.scan_app(roster, page_claims)
        self.roster = roster
        self.target_root: dict[str, tuple[str, str | None]] = {}
        self.composition_root: set[str] = set()
        for row in rows:
            if row["role"] != "production":
                continue
            library_relative = _lib_relative(row["path"])
            self.target_root[library_relative] = derive_target_root(row, roster)
            if is_composition_root(library_relative, row.get("targetPath")):
                self.composition_root.add(library_relative)

    def physical_root(self, library_relative_path: str) -> tuple[str, str | None]:
        """物理树根：`lib/<segment>/...` 的首段落在哪个目标类别。"""
        head = library_relative_path.split("/", 1)[0]
        if head in opm.APP_CROSS_CUTTING_ROOTS:
            return "cross_cutting", head
        if head in self.roster.domains:
            return "domain", head
        return "unresolved", None

    def imports(self, library_relative_path: str) -> list[str]:
        """解析 `import`/`export` 到 lib 相对路径；仅保留指向本包 `lib/**` 的边。"""
        text = (ROOT / opm.APP_LIB_ROOT / library_relative_path).read_text(
            encoding="utf-8", errors="replace"
        )
        resolved: list[str] = []
        for uri in IMPORT_RE.findall(text):
            target = _resolve_import_uri(library_relative_path, uri)
            if target is not None and target in self.target_root:
                resolved.append(target)
        return resolved


def _resolve_import_uri(library_relative_path: str, uri: str) -> str | None:
    if uri.startswith(PACKAGE_URI_PREFIX):
        return uri[len(PACKAGE_URI_PREFIX) :]
    if ":" in uri.split("/", 1)[0]:
        # dart:*、其他 package:* 与 asset scheme 都不构成本包内依赖边。
        return None
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(library_relative_path), uri)
    )


# ---------------------------------------------------------------------------
# R2 / R3：横切面反向 import 禁令
# ---------------------------------------------------------------------------


def _edge(source: str, target: str) -> str:
    return f"{source} -> {target}"


def scan_reverse_import_violations(
    index: AppSourceIndex,
    *,
    physical: bool,
) -> dict[str, list[str]]:
    """按被依赖 domain 聚合横切面 → 业务对象的反向依赖边。

    ``physical=False`` 在目标空间求值（R2），``physical=True`` 在物理空间求值（R3）。
    """
    def classify(library_relative_path: str) -> tuple[str, str | None]:
        if physical:
            return index.physical_root(library_relative_path)
        return index.target_root.get(library_relative_path, ("unresolved", None))

    violations: dict[str, list[str]] = {}
    for library_relative in sorted(index.target_root):
        kind, name = classify(library_relative)
        if kind != "cross_cutting":
            continue
        if library_relative in index.composition_root:
            continue
        for imported in index.imports(library_relative):
            imported_kind, imported_domain = classify(imported)
            if imported_kind != "domain":
                continue
            violations.setdefault(imported_domain, []).append(
                _edge(library_relative, imported)
            )
    return {domain: sorted(edges) for domain, edges in sorted(violations.items())}


# ---------------------------------------------------------------------------
# 违规汇总与基线比对
# ---------------------------------------------------------------------------


def evaluate(roster: opm.ObjectRoster) -> dict:
    """求值三条规则，返回 ``{"shared": {...}, "domains": {...}}``。"""
    index = AppSourceIndex(roster)
    target_reverse = scan_reverse_import_violations(index, physical=False)
    physical_reverse = scan_reverse_import_violations(index, physical=True)

    domains: dict[str, dict[str, list[str]]] = {}
    for domain in sorted(set(target_reverse) | set(physical_reverse)):
        domains[domain] = {
            RULE_TARGET_REVERSE_IMPORT: target_reverse.get(domain, []),
            RULE_PHYSICAL_REVERSE_IMPORT: physical_reverse.get(domain, []),
        }
    return {
        "shared": {RULE_TOP_LEVEL: scan_top_level_violations(roster)},
        "domains": domains,
    }


def load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        raise FileNotFoundError(BASELINE_PATH)
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if document.get("ruleId") != RULE_ID:
        raise ValueError(
            f"{BASELINE_PATH}: ruleId 必须是 {RULE_ID}，实测 {document.get('ruleId')!r}"
        )
    return document


def write_baseline(current: dict, *, domain: str | None) -> None:
    """写入基线；带 `--domain` 时只替换该 domain 分区，避免并行流互相覆盖。"""
    if domain is None:
        payload = {"ruleId": RULE_ID, **_normalized(current)}
    else:
        try:
            payload = load_baseline()
        except (FileNotFoundError, ValueError):
            payload = {"ruleId": RULE_ID, "shared": {}, "domains": {}}
        payload.setdefault("shared", {})
        payload.setdefault("domains", {})
        section = current["domains"].get(domain)
        if section:
            payload["domains"][domain] = section
        else:
            payload["domains"].pop(domain, None)
        payload = {"ruleId": RULE_ID, **_normalized(payload)}
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalized(document: dict) -> dict:
    """规范化违规文档：条目去重排序，空 domain 分区剔除。

    去重是必需的：同一文件同时 `import` 与 `export` 同一目标只算一条依赖边，
    否则写入的基线与集合语义的比对结果会出现计数漂移。
    """
    shared = {
        rule: sorted(set(document.get("shared", {}).get(rule, []) or []))
        for rule in SHARED_RULES
    }
    domains: dict[str, dict[str, list[str]]] = {}
    for domain, section in sorted((document.get("domains") or {}).items()):
        entries = {
            rule: sorted(set(section.get(rule, []) or [])) for rule in DOMAIN_RULES
        }
        if any(entries.values()):
            domains[domain] = entries
    return {"shared": shared, "domains": domains}


def _rule_entries(document: dict, domain: str | None, rule: str) -> set[str]:
    if rule in SHARED_RULES:
        return set(document.get("shared", {}).get(rule, []) or [])
    section = (document.get("domains") or {}).get(domain) or {}
    return set(section.get(rule, []) or [])


def scoped_domains(current: dict, baseline: dict, domain: str | None) -> list[str]:
    if domain is not None:
        return [domain]
    return sorted(set(current.get("domains") or {}) | set(baseline.get("domains") or {}))


def diff(current: dict, baseline: dict, domain: str | None) -> tuple[list[str], list[str]]:
    """返回 ``(new_violations, stale_entries)``，条目已带规则与 domain 前缀。"""
    new_violations: list[str] = []
    stale_entries: list[str] = []

    # R1 是共享的顶层规则，任何 scope 都全量求值，避免并行流各自放行新顶层目录。
    for rule in SHARED_RULES:
        observed = _rule_entries(current, None, rule)
        recorded = _rule_entries(baseline, None, rule)
        new_violations += [f"{rule}: {entry}" for entry in sorted(observed - recorded)]
        stale_entries += [f"{rule}: {entry}" for entry in sorted(recorded - observed)]

    for scoped_domain in scoped_domains(current, baseline, domain):
        for rule in DOMAIN_RULES:
            observed = _rule_entries(current, scoped_domain, rule)
            recorded = _rule_entries(baseline, scoped_domain, rule)
            new_violations += [
                f"{rule}[{scoped_domain}]: {entry}"
                for entry in sorted(observed - recorded)
            ]
            stale_entries += [
                f"{rule}[{scoped_domain}]: {entry}"
                for entry in sorted(recorded - observed)
            ]
    return new_violations, stale_entries


def summarize(current: dict, domain: str | None) -> dict:
    """派生本次求值的违规计数摘要。"""
    domains = scoped_domains(current, {"domains": {}}, domain)
    counts = {rule: len(_rule_entries(current, None, rule)) for rule in SHARED_RULES}
    for rule in DOMAIN_RULES:
        counts[rule] = sum(
            len(_rule_entries(current, scoped_domain, rule))
            for scoped_domain in domains
        )
    by_domain = {
        scoped_domain: {
            rule: len(_rule_entries(current, scoped_domain, rule))
            for rule in DOMAIN_RULES
        }
        for scoped_domain in domains
        if any(_rule_entries(current, scoped_domain, rule) for rule in DOMAIN_RULES)
    }
    return {
        "ruleId": RULE_ID,
        "scope": domain or "all",
        "violations": counts,
        "violationsByDomain": by_domain,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="端侧对象化架构门禁 v1（顶层白名单 + 横切面反向 import 禁令）"
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="只比对该 domain 名下的 R2/R3 违规；R1 顶层规则始终全量求值",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="用当前违规重写基线；搭配 --domain 时只重写该 domain 分区",
    )
    arguments = parser.parse_args(argv)

    roster = load_roster()
    if arguments.domain is not None and arguments.domain not in roster.domains:
        print(
            f"verify_app_architecture: BLOCK: 未知 domain {arguments.domain!r}，"
            f"ContractGraph roster 只有 {sorted(roster.domains)}",
            file=sys.stderr,
        )
        return 2

    current = _normalized(evaluate(roster))

    if arguments.write_baseline:
        write_baseline(current, domain=arguments.domain)
        summary = summarize(current, arguments.domain)
        print(
            "verify_app_architecture: wrote baseline "
            f"scope={summary['scope']} -> {BASELINE_PATH}"
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0

    try:
        baseline = load_baseline()
    except FileNotFoundError:
        print(
            "verify_app_architecture: BLOCK: missing "
            f"{BASELINE_PATH} (run once with --write-baseline)",
            file=sys.stderr,
        )
        return 2
    except (ValueError, json.JSONDecodeError) as error:
        print(f"verify_app_architecture: FAIL load baseline: {error}", file=sys.stderr)
        return 1

    new_violations, stale_entries = diff(current, baseline, arguments.domain)
    if new_violations or stale_entries:
        print("verify_app_architecture: BLOCK: baseline drift", file=sys.stderr)
        for entry in new_violations:
            print(f"  new violation: {entry}", file=sys.stderr)
        for entry in stale_entries:
            print(f"  stale baseline entry: {entry}", file=sys.stderr)
        print(
            "  lib/ 顶层只允许 <domain>/、runtime/、design_system/、l10n/ 与 "
            "main*.dart；runtime/** 与 design_system/** 不得依赖任何 "
            "lib/<domain>/**（组合根 runtime/di/** 与入口除外）。"
            "违规消失后用 --write-baseline 收敛基线。",
            file=sys.stderr,
        )
        return 1

    summary = summarize(current, arguments.domain)
    print(f"verify_app_architecture: OK (scope={summary['scope']})")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

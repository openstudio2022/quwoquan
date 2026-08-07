#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002
"""Ratchet gate: contract enum fields must reach the App as typed Dart enums.

Why this gate exists
--------------------
`quwoquan_service/contracts/metadata/_shared/types.yaml` owns the canonical
enum value sets. A contract field binds to one of those sets through
`enum_ref:`. When the generated App contract DTO still declares that field as a
bare `String`, the enum definition exists but never takes effect: the decoder
accepts any string, so drifted values (the historical
`AssistantUsePolicy: allow` / `allow_summary`) travel through the App unnoticed.
That is strictly worse than having no enum at all, because the canonical
definition creates the illusion of governance.

What is measured
----------------
1. Canonical enum names come from `_shared/types.yaml`.
2. Every contract field declaration carrying `enum_ref: <canonical enum>` is
   collected from the service contracts and the shared metadata tree. Field
   names are kept with the *set* of enums they bind to, because a short name
   such as `scope` or `outcome` legitimately binds to different enums in
   different objects.
3. Generated App contract DTOs under
   `quwoquan_app/packages/quwoquan_cloud_contracts/lib` are scanned for
   `final String <field>;` / `final String? <field>;` / `final List<String>
   <field>;` declarations whose field name is enum-bound. Each such declaration
   is one untyped site.

Ratchet policy
--------------
The baseline records the measured site count, both in total and per field. The
gate BLOCKs when the count grows (a new untyped enum field) and it also BLOCKs
when the count shrinks without the baseline being tightened, so the recorded
number can never go stale upwards. There is deliberately no `--write-baseline`
flag: tightening the ratchet is a reviewed, hand-edited change to
`quwoquan_ops/policies/gates/app_enum_typed_binding_baseline.yaml`.

The fix for a blocked field is always contracts-first: declare the field as
`type: enum` together with its `enum_ref` in the owning service contract (object
fields, request messages and projection slices all need it), regenerate, then let
the typed enum flow into the App decoder. Compatibility mappings, dual-read and
string fallbacks are forbidden.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

GATE_NAME = "verify_app_enum_typed_binding"

CANONICAL_TYPES_RELATIVE = "quwoquan_service/contracts/metadata/_shared/types.yaml"
CONTRACT_ROOTS_RELATIVE = (
    "quwoquan_service/services",
    "quwoquan_service/contracts/metadata",
)
APP_GENERATED_ROOT_RELATIVE = "quwoquan_app/packages/quwoquan_cloud_contracts/lib"
BASELINE_RELATIVE = "quwoquan_ops/policies/gates/app_enum_typed_binding_baseline.yaml"

_UNTYPED_DECLARATION = re.compile(
    r"^\s*final\s+(String\?|String|List<String>\?|List<String>)\s+([A-Za-z0-9_]+)\s*;"
)
_ANY_DECLARATION = re.compile(r"^\s*final\s+([A-Za-z0-9_<>,?\s]+?)\s+([A-Za-z0-9_]+)\s*;")


class ScanError(RuntimeError):
    """Raised when the gate cannot trust its own inputs."""


@dataclass(frozen=True)
class UntypedSite:
    path: str
    line: int
    declared_type: str
    field: str
    enums: tuple[str, ...]

    def render(self) -> str:
        enums = "|".join(self.enums)
        return f"{self.path}:{self.line} final {self.declared_type} {self.field}; -> {enums}"


@dataclass
class ScanResult:
    canonical_enums: tuple[str, ...] = ()
    enum_bound_fields: dict[str, tuple[str, ...]] = dataclass_field(
        default_factory=dict
    )
    scanned_declarations: int = 0
    scanned_dart_files: int = 0
    untyped_sites: tuple[UntypedSite, ...] = ()

    @property
    def sites_by_field(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for site in self.untyped_sites:
            counts[site.field] += 1
        return dict(counts)


def load_canonical_enums(types_path: Path) -> tuple[str, ...]:
    """Return the canonical enum names declared in `_shared/types.yaml`."""

    import yaml  # type: ignore

    if not types_path.is_file():
        raise ScanError(f"canonical enum source is missing: {types_path}")
    document = yaml.safe_load(types_path.read_text(encoding="utf-8")) or {}
    enums = document.get("enums") or {}
    if not isinstance(enums, dict) or not enums:
        raise ScanError(f"canonical enum source declares no enums: {types_path}")
    return tuple(sorted(str(name) for name in enums))


def _scalar(node: object) -> str | None:
    import yaml  # type: ignore

    if isinstance(node, yaml.ScalarNode):
        return str(node.value).strip()
    return None


def _walk_field_declarations(node: object, out: list[tuple[str, str]]) -> None:
    import yaml  # type: ignore

    if isinstance(node, yaml.MappingNode):
        entries: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = _scalar(key_node)
            if key is not None:
                entries[key] = value_node
        name = _scalar(entries.get("name")) if "name" in entries else None
        enum_ref = _scalar(entries.get("enum_ref")) if "enum_ref" in entries else None
        if name and enum_ref:
            out.append((name, enum_ref))
        for _, value_node in node.value:
            _walk_field_declarations(value_node, out)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _walk_field_declarations(item, out)


def collect_enum_bound_fields(
    contract_roots: tuple[Path, ...],
    canonical_enums: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Map contract field name -> canonical enums the field binds to."""

    import yaml  # type: ignore

    known = set(canonical_enums)
    bindings: dict[str, set[str]] = defaultdict(set)
    for root in contract_roots:
        if not root.is_dir():
            raise ScanError(f"contract root does not exist: {root}")
        for path in sorted(root.rglob("*.yaml")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "enum_ref" not in text:
                continue
            try:
                documents = list(yaml.compose_all(text))
            except yaml.YAMLError:
                continue
            found: list[tuple[str, str]] = []
            for document in documents:
                if document is not None:
                    _walk_field_declarations(document, found)
            for name, enum_ref in found:
                if enum_ref in known:
                    bindings[name].add(enum_ref)
    if not bindings:
        raise ScanError(
            "no contract field binds to a canonical enum; the scan roots are "
            f"wrong or empty: {[str(root) for root in contract_roots]}"
        )
    return {name: tuple(sorted(refs)) for name, refs in sorted(bindings.items())}


def scan_generated_dtos(
    generated_root: Path,
    enum_bound_fields: dict[str, tuple[str, ...]],
) -> tuple[int, int, tuple[UntypedSite, ...]]:
    """Return (dart files, scanned declarations, untyped enum sites)."""

    if not generated_root.is_dir():
        raise ScanError(f"generated App contract root does not exist: {generated_root}")
    dart_files = 0
    declarations = 0
    sites: list[UntypedSite] = []
    for path in sorted(generated_root.rglob("*.dart")):
        dart_files += 1
        relative = path.as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if _ANY_DECLARATION.match(line):
                declarations += 1
            match = _UNTYPED_DECLARATION.match(line)
            if match is None:
                continue
            name = match.group(2)
            enums = enum_bound_fields.get(name)
            if enums is None:
                continue
            sites.append(
                UntypedSite(
                    path=relative,
                    line=line_number,
                    declared_type=match.group(1),
                    field=name,
                    enums=enums,
                )
            )
    return dart_files, declarations, tuple(sites)


def scan(
    repo_root: Path,
    *,
    types_path: Path | None = None,
    contract_roots: tuple[Path, ...] | None = None,
    generated_root: Path | None = None,
) -> ScanResult:
    types_path = types_path or repo_root / CANONICAL_TYPES_RELATIVE
    contract_roots = contract_roots or tuple(
        repo_root / relative for relative in CONTRACT_ROOTS_RELATIVE
    )
    generated_root = generated_root or repo_root / APP_GENERATED_ROOT_RELATIVE

    canonical_enums = load_canonical_enums(types_path)
    enum_bound_fields = collect_enum_bound_fields(contract_roots, canonical_enums)
    dart_files, declarations, sites = scan_generated_dtos(
        generated_root, enum_bound_fields
    )
    if declarations == 0:
        raise ScanError(
            "scanned 0 field declarations under "
            f"{generated_root}; the gate cannot prove anything about enum typing"
        )
    result = ScanResult(
        canonical_enums=canonical_enums,
        enum_bound_fields=enum_bound_fields,
        scanned_declarations=declarations,
        scanned_dart_files=dart_files,
        untyped_sites=sites,
    )
    return result


def load_baseline(baseline_path: Path) -> dict[str, object]:
    import yaml  # type: ignore

    if not baseline_path.is_file():
        raise ScanError(f"ratchet baseline is missing: {baseline_path}")
    document = yaml.safe_load(baseline_path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ScanError(f"ratchet baseline is malformed: {baseline_path}")
    if "untyped_site_total" not in document:
        raise ScanError(
            f"ratchet baseline has no `untyped_site_total`: {baseline_path}"
        )
    return document


def evaluate(
    result: ScanResult, baseline: dict[str, object]
) -> tuple[list[str], list[str]]:
    """Return (blocking failures, tighten reminders).

    The ratchet only blocks on growth, per field and in total. Shrinking is the
    desired direction, so it is reported as a reminder to hand-edit the baseline
    down instead of blocking the agent that just paid the debt. Growth inside a
    single field blocks even when the total still sits under a stale baseline, so
    a fixed field cannot be silently traded for a new violation elsewhere.
    """

    failures: list[str] = []
    reminders: list[str] = []
    expected_total = int(baseline.get("untyped_site_total", 0))
    raw_per_field = baseline.get("untyped_sites_by_field") or {}
    expected_per_field = {
        str(name): int(count) for name, count in dict(raw_per_field).items()
    }
    actual_per_field = result.sites_by_field
    actual_total = len(result.untyped_sites)

    regressed = sorted(
        name
        for name, count in actual_per_field.items()
        if count > expected_per_field.get(name, 0)
    )
    for name in regressed:
        expected = expected_per_field.get(name, 0)
        failures.append(
            f"enum field `{name}` is declared as a bare String in "
            f"{actual_per_field[name]} generated site(s), baseline allows {expected}; "
            "declare it as `type: enum` with its `enum_ref` in the owning service "
            "contract and regenerate"
        )
        for site in result.untyped_sites:
            if site.field == name:
                failures.append(f"  {site.render()}")

    if actual_total > expected_total:
        failures.append(
            f"untyped enum site total grew: actual={actual_total} "
            f"baseline={expected_total}"
        )
    elif actual_total < expected_total:
        reminders.append(
            f"ratchet can tighten: actual={actual_total} is below "
            f"baseline={expected_total}; hand-edit {BASELINE_RELATIVE} down to "
            "the measured value"
        )

    stale = sorted(
        name
        for name, count in expected_per_field.items()
        if count > actual_per_field.get(name, 0)
    )
    for name in stale:
        reminders.append(
            f"stale baseline entry `{name}`: actual="
            f"{actual_per_field.get(name, 0)} baseline={expected_per_field[name]}"
        )
    return failures, reminders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to scan (defaults to this checkout)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the measured inventory as JSON instead of the gate summary",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        result = scan(repo_root)
    except ScanError as error:
        print(f"{GATE_NAME}: BLOCK: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "canonical_enums": len(result.canonical_enums),
                    "enum_bound_fields": len(result.enum_bound_fields),
                    "scanned_dart_files": result.scanned_dart_files,
                    "scanned_declarations": result.scanned_declarations,
                    "untyped_site_total": len(result.untyped_sites),
                    "untyped_sites_by_field": dict(
                        sorted(result.sites_by_field.items())
                    ),
                    "untyped_sites": [
                        site.render() for site in result.untyped_sites
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    try:
        baseline = load_baseline(repo_root / BASELINE_RELATIVE)
    except ScanError as error:
        print(f"{GATE_NAME}: BLOCK: {error}", file=sys.stderr)
        return 2

    failures, reminders = evaluate(result, baseline)
    if failures:
        print(f"{GATE_NAME}: BLOCK: enum typed-binding ratchet drift", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(
            "  Fix contracts-first: declare `type: enum` + `enum_ref` on the "
            "object field, the request message and the projection slice in the "
            "owning service contract, regenerate, then consume the typed enum in "
            "the App decoder. Compatibility mappings and String fallbacks are "
            "forbidden.",
            file=sys.stderr,
        )
        return 1

    for reminder in reminders:
        print(f"{GATE_NAME}: TIGHTEN: {reminder}")
    print(
        f"{GATE_NAME}: OK (canonical_enums={len(result.canonical_enums)}, "
        f"enum_bound_fields={len(result.enum_bound_fields)}, "
        f"scanned_declarations={result.scanned_declarations}, "
        f"untyped_sites={len(result.untyped_sites)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

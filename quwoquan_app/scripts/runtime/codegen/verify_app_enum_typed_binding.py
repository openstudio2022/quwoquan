#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002
"""Gate: contract enum fields must reach the App as typed Dart enums.

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
The generator emits `quwoquan_app/tool/cloud_codegen/field_binding_report.json`,
which records every generated Dart field whose owning contract declaration
carries an `enum_ref`, together with the Dart type that was actually emitted.
This gate reads that report and blocks on any binding where the emitted type is
not the enum.

The report replaces an earlier field-name heuristic that matched generated
field names against every `enum_ref` in the contract tree. Field names are not
unique across objects: `status` binds 27 different canonical enums depending on
the owner, and `kind` on an assistant runtime failure has nothing to do with
`CircleKind`. That heuristic reported 215 sites of which only 9 were real, so
the number it produced could neither be trusted nor driven to zero. Only the
generator knows which contract declaration produced which Dart field, so it now
states the binding and this gate verifies it.

This is a zero-gap gate: there is no baseline and no budget. Once the precise
measure was in place the real debt turned out to be nine sites, all of which
were paid off, so any untyped binding from here on is a new regression rather
than inherited debt.

Fixing a blocked field is always contracts-first: declare the field as
`type: enum` together with its `enum_ref` in the owning service contract (object
fields, request messages and projection slices all need it), make sure the enum
is registered in the catalog its renderer reads, regenerate, then let the typed
enum flow into the App decoder. Compatibility mappings, dual-read and string
fallbacks are forbidden.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

GATE_NAME = "verify_app_enum_typed_binding"

REPORT_RELATIVE = "quwoquan_app/tool/cloud_codegen/field_binding_report.json"

# The report has to keep covering the renderers that historically emitted
# untyped enum fields. If a renderer stops recording its bindings the gate would
# go green while losing sight of a whole tree, so an empty or shrunken scan is
# itself a blocking condition.
REQUIRED_COVERAGE = (
    "packages/quwoquan_cloud_contracts/lib/src/content/content_operation_contracts.g.dart",
    "packages/quwoquan_cloud_contracts/lib/src/generated/requests/content/"
    "content_operation_contracts.g.requests.g.dart",
    "packages/quwoquan_cloud_contracts/lib/src/generated/assistant/"
    "assistant_api_responses.g.dart",
)


class ScanError(RuntimeError):
    """Raised when the gate cannot trust its own inputs."""


@dataclass(frozen=True)
class UntypedSite:
    generated_path: str
    dart_class: str
    dart_field: str
    dart_type: str
    enum_ref: str
    contract_type: str
    client_dart_type: str

    @property
    def key(self) -> str:
        return f"{self.dart_class}.{self.dart_field}"

    def render(self) -> str:
        detail = f"contract type={self.contract_type or '(unset)'}"
        if self.client_dart_type:
            detail += f", client_dart_type={self.client_dart_type}"
        return (
            f"{self.key} -> {self.enum_ref} emitted as `{self.dart_type}` "
            f"({detail}) in {self.generated_path}"
        )


@dataclass
class ScanResult:
    total_bindings: int = 0
    typed_bindings: int = 0
    covered_files: int = 0
    untyped_sites: tuple[UntypedSite, ...] = ()

    @property
    def sites_by_key(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for site in self.untyped_sites:
            counts[site.key] = counts.get(site.key, 0) + 1
        return counts


def scan(repo_root: Path, *, report_path: Path | None = None) -> ScanResult:
    report_path = report_path or repo_root / REPORT_RELATIVE
    if not report_path.is_file():
        raise ScanError(
            f"field binding report is missing: {report_path}; run `make codegen-app` "
            "so the generator states which contract enum_ref produced which Dart field"
        )
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ScanError(f"field binding report is malformed: {report_path}: {error}")
    if not isinstance(document, dict):
        raise ScanError(f"field binding report root must be an object: {report_path}")
    bindings = document.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ScanError(
            f"field binding report declares no bindings: {report_path}; the gate "
            "cannot prove anything about enum typing"
        )

    sites: list[UntypedSite] = []
    typed = 0
    covered: set[str] = set()
    for entry in bindings:
        if not isinstance(entry, dict):
            raise ScanError(f"field binding report has a non-object entry: {entry!r}")
        enum_ref = str(entry.get("enumRef") or "").strip()
        if not enum_ref:
            raise ScanError(
                f"field binding report entry has no enumRef: {entry!r}; the report "
                "must only contain enum-bound fields"
            )
        generated_path = str(entry.get("generatedPath") or "").strip()
        if not generated_path:
            raise ScanError(
                f"field binding report entry has no generatedPath: {entry!r}; a "
                "renderer recorded a binding without ever writing its file"
            )
        covered.add(generated_path)
        if bool(entry.get("typed")):
            typed += 1
            continue
        sites.append(
            UntypedSite(
                generated_path=generated_path,
                dart_class=str(entry.get("dartClass") or "").strip(),
                dart_field=str(entry.get("dartField") or "").strip(),
                dart_type=str(entry.get("dartType") or "").strip(),
                enum_ref=enum_ref,
                contract_type=str(entry.get("contractType") or "").strip(),
                client_dart_type=str(entry.get("clientDartType") or "").strip(),
            )
        )

    missing_coverage = [path for path in REQUIRED_COVERAGE if path not in covered]
    if missing_coverage:
        raise ScanError(
            "field binding report no longer covers "
            f"{missing_coverage}; a renderer stopped recording its enum bindings"
        )

    return ScanResult(
        total_bindings=len(bindings),
        typed_bindings=typed,
        covered_files=len(covered),
        untyped_sites=tuple(sites),
    )


def evaluate(result: ScanResult) -> list[str]:
    """Return the blocking failures.

    Every enum-bound field must reach the App as its enum. There is no budget:
    a contract that declares `enum_ref` and then hands the App a bare String
    gives the value set the appearance of governance while accepting anything.
    """

    failures: list[str] = []
    for name in sorted(result.sites_by_key):
        failures.append(
            f"`{name}` binds a canonical enum but is generated as a bare String"
        )
        for site in result.untyped_sites:
            if site.key == name:
                failures.append(f"  {site.render()}")
    return failures


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
                    "total_bindings": result.total_bindings,
                    "typed_bindings": result.typed_bindings,
                    "covered_files": result.covered_files,
                    "untyped_site_total": len(result.untyped_sites),
                    "untyped_sites_by_field": dict(sorted(result.sites_by_key.items())),
                    "untyped_sites": [
                        site.render() for site in result.untyped_sites
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    failures = evaluate(result)
    if failures:
        print(
            f"{GATE_NAME}: BLOCK: contract enum reaches the App as a bare String",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(
            "  Fix contracts-first: declare `type: enum` + `enum_ref` on the "
            "object field, the request message and the projection slice in the "
            "owning service contract, register the enum in the catalog its "
            "renderer reads, regenerate, then consume the typed enum in the App "
            "decoder. Compatibility mappings and String fallbacks are forbidden.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{GATE_NAME}: OK (bindings={result.total_bindings}, "
        f"typed={result.typed_bindings}, files={result.covered_files}, "
        f"untyped_sites={len(result.untyped_sites)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

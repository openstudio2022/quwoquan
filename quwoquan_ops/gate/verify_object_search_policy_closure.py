#!/usr/bin/env python3
"""Make searchability a fail-closed contract fact instead of three hand-synced lists.

Before this gate, whether an object was searchable was decided in three places
that nothing tied together: the 12 `search_objects.yaml` registrations, each
owner service's ES projector, and each domain's `*SearchEligible()` predicate.
Adding an object required nobody to say anything, so the default came from
whichever implementation happened to touch it.

`object.yaml.search_policy` is now the single declaration and this gate is what
makes it binding:

* Fail-closed authoring — every object on disk must declare `search_policy`, and
  the shape required for each `exposed` value differs, so "forgot to think about
  it" cannot be spelled the same way as "deliberately closed".
* Live references — `eligibility_ref` / `index_projector_ref` /
  `provider_egress_ref` / `privacy_filter_ref` must resolve to a real Go function
  or method. A renamed or deleted projector breaks the gate instead of silently
  leaving a declaration pointing at nothing.
* Registration closure — `search_objects.yaml` and the object contracts must
  agree in both directions: every registration names an owner object that claims
  the same object type, and no object claims a type nobody registered.
* Projector evidence — every registration whose owner actually produces documents
  must have a Go test that names the projector or egress entry point.

The two `remote_*` values are deliberately separate. `remote_index` means this
object's own data lands in the shared index, so an index projector and an
eligibility predicate must exist. `remote_provider` means results come live from
a third party through this object's egress and nothing of ours is indexed, so
demanding an index projector would only invite a fake one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_OBJECTS_RELATIVE = (
    "quwoquan_service/contracts/metadata/_shared/search_objects.yaml"
)

EXPOSED_VALUES = (
    "none",
    "filter_only",
    "local_only",
    "remote_index",
    "remote_provider",
    "hybrid",
)

# `execution_strategy` is the App-facing projection of the same fact; the object
# contract is authoritative and this table is the only permitted correspondence.
STRATEGY_BY_EXPOSED = {
    "remote_index": "remote_only",
    "remote_provider": "remote_only",
    "hybrid": "hybrid_remote_fallback_local",
    "local_only": "local_only",
    "filter_only": "filter_only",
}

REQUIRED_REFS = {
    "remote_index": ("eligibility_ref", "index_projector_ref", "privacy_filter_ref"),
    "hybrid": ("eligibility_ref", "index_projector_ref", "privacy_filter_ref"),
    "remote_provider": ("provider_egress_ref", "privacy_filter_ref"),
}
FORBIDDEN_REFS = {
    "none": (
        "object_type_refs",
        "eligibility_ref",
        "index_projector_ref",
        "provider_egress_ref",
        "privacy_filter_ref",
        "delegated_enforcement",
    ),
    "local_only": (
        "eligibility_ref",
        "index_projector_ref",
        "provider_egress_ref",
        "privacy_filter_ref",
    ),
    "filter_only": (
        "eligibility_ref",
        "index_projector_ref",
        "provider_egress_ref",
        "privacy_filter_ref",
    ),
}
# The reference whose existence must be proven by a Go test, per exposure.
TESTED_REF = {
    "remote_index": "index_projector_ref",
    "hybrid": "index_projector_ref",
    "remote_provider": "provider_egress_ref",
}


class ScanError(Exception):
    """Raised when the scan itself cannot be trusted, never for a policy failure."""


def object_paths(repo_root: Path) -> list[Path]:
    service_root = repo_root / "quwoquan_service"
    if not service_root.is_dir():
        raise ScanError(f"service root does not exist: {service_root}")
    found = set(service_root.glob("*/*/contracts/*/*/object.yaml"))
    found |= set(service_root.glob("*/*/*/contracts/*/*/object.yaml"))
    return sorted(found)


def domain_of(contracts_root: Path) -> str:
    document = contracts_root / "domain.yaml"
    if not document.is_file():
        raise ScanError(f"missing domain declaration: {document}")
    match = re.search(
        r"^domain:\s*(\S+)\s*$", document.read_text(encoding="utf-8"), re.MULTILINE
    )
    if not match:
        raise ScanError(f"no `domain:` key in {document}")
    return match.group(1)


def object_id_of(path: Path) -> str:
    return domain_of(path.parents[2]) + "." + path.parents[0].name.replace("-", "_")


def load_objects(repo_root: Path) -> dict[str, tuple[Path, dict]]:
    paths = object_paths(repo_root)
    if not paths:
        raise ScanError(
            f"scanned 0 object.yaml under {repo_root / 'quwoquan_service'}; "
            "an empty scan can never be reported as a pass"
        )
    objects: dict[str, tuple[Path, dict]] = {}
    for path in paths:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ScanError(f"{path}: {error}") from error
        if not isinstance(document, dict):
            raise ScanError(f"{path}: object.yaml must be a mapping")
        object_id = object_id_of(path)
        if object_id in objects:
            raise ScanError(
                f"duplicate object id {object_id}: {objects[object_id][0]} and {path}"
            )
        objects[object_id] = (path, document)
    return objects


def resolve_go_symbol(repo_root: Path, reference: str) -> str | None:
    """Return a failure string when `<path>#<Symbol>` does not resolve.

    `<Symbol>` is either a plain function name, or a receiver-qualified method
    `Type.Method` for projectors implemented as methods on an event/aggregate
    type (e.g. `UserProfileSearchProjectionEvent.Document`).
    """
    if "#" not in reference:
        return f"reference {reference!r} must use `<repo-relative path>#<GoSymbol>`"
    relative, symbol = reference.rsplit("#", 1)
    target = repo_root / relative
    if not target.is_file():
        return f"reference {reference!r} points at a missing file"
    body = target.read_text(encoding="utf-8")
    if "." in symbol:
        receiver_type, method_name = symbol.rsplit(".", 1)
        bound = re.compile(
            rf"^func\s+\([^)]*\*?{re.escape(receiver_type)}\s*\)"
            rf"\s*{re.escape(method_name)}\s*[\(\[]",
            re.MULTILINE,
        )
        if bound.search(body):
            return None
        return (
            f"reference {reference!r} has no "
            f"`func (... {receiver_type}) {method_name}` definition"
        )
    # Plain function, or a method on any receiver. Nothing else counts: a comment
    # or a call site mentioning the name is not a definition.
    plain = re.compile(rf"^func\s+{re.escape(symbol)}\s*[\(\[]", re.MULTILINE)
    method = re.compile(rf"^func\s+\([^)]*\)\s*{re.escape(symbol)}\s*[\(\[]", re.MULTILINE)
    if plain.search(body) or method.search(body):
        return None
    return f"reference {reference!r} has no `func {symbol}` definition"


def go_test_names(repo_root: Path) -> dict[str, set[str]]:
    """Map every Go test file to the identifiers it mentions, per service."""
    index: dict[str, set[str]] = {}
    for path in (repo_root / "quwoquan_service").rglob("*_test.go"):
        try:
            index[str(path)] = set(
                re.findall(r"[A-Za-z_][A-Za-z0-9_]*", path.read_text(encoding="utf-8"))
            )
        except OSError as error:
            raise ScanError(f"{path}: {error}") from error
    if not index:
        raise ScanError("scanned 0 Go test files; projector evidence cannot be proven")
    return index


def validate_declarations(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> list[str]:
    failures: list[str] = []
    for object_id, (path, document) in sorted(objects.items()):
        policy = document.get("search_policy")
        if policy is None:
            failures.append(
                f"{object_id}: no search_policy declared ({path.relative_to(repo_root)}); "
                "search exposure is fail-closed and must be stated explicitly"
            )
            continue
        if not isinstance(policy, dict):
            failures.append(f"{object_id}: search_policy must be a mapping")
            continue
        exposed = policy.get("exposed")
        if exposed not in EXPOSED_VALUES:
            failures.append(
                f"{object_id}: search_policy.exposed={exposed!r} is not in "
                f"{list(EXPOSED_VALUES)}"
            )
            continue
        for key in FORBIDDEN_REFS.get(exposed, ()):
            if key in policy:
                failures.append(
                    f"{object_id}: exposed={exposed} must not declare {key}"
                )
        if exposed == "none":
            if not str(policy.get("not_exposed_reason", "")).strip():
                failures.append(
                    f"{object_id}: exposed=none requires not_exposed_reason"
                )
        elif "not_exposed_reason" in policy:
            failures.append(
                f"{object_id}: not_exposed_reason is only valid for exposed=none"
            )
        if exposed in ("local_only", "filter_only") and not str(
            policy.get("delegated_enforcement", "")
        ).strip():
            failures.append(
                f"{object_id}: exposed={exposed} requires delegated_enforcement "
                "naming where the visibility gate actually lives"
            )
        for key in REQUIRED_REFS.get(exposed, ()):
            reference = str(policy.get(key, "")).strip()
            if not reference:
                failures.append(f"{object_id}: exposed={exposed} requires {key}")
                continue
            problem = resolve_go_symbol(repo_root, reference)
            if problem:
                failures.append(f"{object_id}.{key}: {problem}")
    return failures


def validate_registration_closure(
    repo_root: Path,
    objects: dict[str, tuple[Path, dict]],
    registry: dict,
    tests: dict[str, set[str]],
) -> list[str]:
    failures: list[str] = []
    entries = registry.get("object_types")
    if not isinstance(entries, list) or not entries:
        raise ScanError("search_objects.yaml declares no object_types")

    claimed: dict[str, list[str]] = {}
    for object_id, (_, document) in objects.items():
        for reference in document.get("search_policy", {}).get("object_type_refs", []):
            claimed.setdefault(str(reference), []).append(object_id)

    registered: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(f"object_types[{index}] must be a mapping")
            continue
        type_id = str(entry.get("id", "")).strip()
        if not type_id:
            failures.append(f"object_types[{index}] has no id")
            continue
        registered.add(type_id)
        owner = str(entry.get("owner_object", "")).strip()
        if not owner:
            failures.append(
                f"{type_id}: no owner_object; every registration must name the "
                "business object whose contract governs it"
            )
            continue
        if owner not in objects:
            failures.append(
                f"{type_id}: owner_object={owner} is not an object on disk"
            )
            continue
        policy = objects[owner][1].get("search_policy", {})
        exposed = policy.get("exposed")
        if exposed == "none":
            failures.append(
                f"{type_id}: owner {owner} declares exposed=none but is registered "
                "as a searchable object type"
            )
            continue
        if type_id not in claimed.get(type_id, []) and owner not in claimed.get(
            type_id, []
        ):
            failures.append(
                f"{type_id}: owner {owner} does not list it in "
                "search_policy.object_type_refs"
            )
            continue
        strategy = str(entry.get("execution_strategy", "")).strip()
        expected = STRATEGY_BY_EXPOSED.get(exposed)
        if strategy != expected:
            failures.append(
                f"{type_id}: execution_strategy={strategy!r} disagrees with owner "
                f"{owner} exposed={exposed} (expected {expected!r})"
            )
        tested_key = TESTED_REF.get(exposed)
        if tested_key is None:
            continue
        reference = str(policy.get(tested_key, "")).strip()
        if "#" not in reference:
            continue
        symbol = reference.rsplit("#", 1)[1]
        # A `Type.Method` reference is evidenced by a test that names both the
        # receiver type and the method in the same file; identifiers cannot
        # contain a dot, so the joined literal would never match.
        required = set(symbol.split(".")) if "." in symbol else {symbol}
        if not any(required <= names for names in tests.values()):
            failures.append(
                f"{type_id}: no Go test names {symbol} ({tested_key} of {owner}); "
                "a registered searchable type must have projector evidence"
            )

    for type_id, owners in sorted(claimed.items()):
        if len(owners) > 1:
            failures.append(
                f"{type_id}: claimed by multiple objects {sorted(owners)}; "
                "each object type has exactly one owner"
            )
        if type_id not in registered:
            failures.append(
                f"{type_id}: claimed by {owners[0]} but not registered in "
                "search_objects.yaml"
            )
    return failures


def run(repo_root: Path) -> tuple[int, list[str], int]:
    objects = load_objects(repo_root)
    registry_path = repo_root / SEARCH_OBJECTS_RELATIVE
    if not registry_path.is_file():
        raise ScanError(f"missing search registry: {registry_path}")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        raise ScanError(f"{registry_path}: expected a mapping")
    failures = validate_declarations(repo_root, objects)
    failures += validate_registration_closure(
        repo_root, objects, registry, go_test_names(repo_root)
    )
    return len(objects), failures, len(registry.get("object_types") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    arguments = parser.parse_args(argv)
    repo_root = Path(arguments.repo_root).resolve()
    try:
        scanned, failures, registrations = run(repo_root)
    except ScanError as error:
        print(f"[search-policy] FAIL: {error}")
        return 1
    except (OSError, yaml.YAMLError) as error:
        print(f"[search-policy] FAIL: {error}")
        return 1
    if failures:
        for failure in failures:
            print(f"[search-policy] FAIL: {failure}")
        print(f"[search-policy] GATE_BLOCK: {len(failures)} failure(s)")
        return 1
    print(
        f"[search-policy] OK: objects={scanned} registrations={registrations}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

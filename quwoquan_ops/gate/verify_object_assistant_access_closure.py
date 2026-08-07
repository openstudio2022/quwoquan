#!/usr/bin/env python3
"""Make 小趣 (Assistant) exposure a fail-closed contract fact.

Only one object in the repository (`content.post`) ever declared an assistant
policy. Every other object's exposure was decided by implementation-side
filtering, and the assistant's cross-domain reach came from a hand-written
`DomainReaderDescriptor` slice in `descriptors.go` that no contract referenced.
Adding an object therefore forced nobody to take a position.

`object.yaml.assistant_access` is now the declaration; this gate makes it binding.

* Fail-closed authoring — every object must state `read` / `cite` / `write`, and
  an object that is closed on all three must say why. "Nobody decided" and
  "deliberately closed" cannot be spelled the same way.
* Scope grammar — each granted capability carries exactly the scope derived from
  the object's own identity (`assistant.<domain>.<object>.<capability>`). Pasting
  a sibling object's scope in is rejected, so a grant cannot quietly widen.
* Consent coupling — any write capability must set `requires_user_consent` and a
  `consent_scope_ref` equal to its own write scope, which is what the existing
  SkillConsent grant records and the ApproveTool prompt are keyed on.
* Descriptor derivation — every object type reachable through a
  `DomainReaderDescriptor` must be an object on disk whose `read` is open. This is
  what stops the descriptor catalogue from drifting away from the contract graph.
* Privacy coupling — `privacy.yaml.field_visibility` may only name `assistant` as
  a consumer when the object's `read` is actually open.

`cite` is separate from `read` on purpose. Reading an object into the assistant's
working context and reproducing it inside a user-visible answer are different
disclosures: a private message can legitimately inform an answer while never
being quotable, and collapsing the two would force one of those to be wrong.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTORS_RELATIVE = (
    "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/"
    "infrastructure/skillcontext/descriptors.go"
)

READ_MODES = ("none", "metadata_only", "owner_scoped", "public")
CITE_MODES = ("none", "internal_reference", "public_citation")
WRITE_MODES = ("none", "proposal_only", "consented_command")
MODES = {"read": READ_MODES, "cite": CITE_MODES, "write": WRITE_MODES}


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
        object_id = domain_of(path.parents[2]) + "." + path.parents[0].name.replace(
            "-", "_"
        )
        if object_id in objects:
            raise ScanError(f"duplicate object id {object_id}")
        objects[object_id] = (path, document)
    return objects


def pascal_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def validate_declarations(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> list[str]:
    failures: list[str] = []
    for object_id, (path, document) in sorted(objects.items()):
        access = document.get("assistant_access")
        if access is None:
            failures.append(
                f"{object_id}: no assistant_access declared "
                f"({path.relative_to(repo_root)}); assistant exposure is fail-closed "
                "and an undeclared object is not implicitly open"
            )
            continue
        if not isinstance(access, dict):
            failures.append(f"{object_id}: assistant_access must be a mapping")
            continue
        domain, local = object_id.split(".", 1)
        modes: dict[str, str] = {}
        for capability, allowed in MODES.items():
            block = access.get(capability)
            if not isinstance(block, dict):
                failures.append(
                    f"{object_id}: assistant_access.{capability} must be a mapping "
                    "declaring mode and scopes"
                )
                continue
            mode = block.get("mode")
            if mode not in allowed:
                failures.append(
                    f"{object_id}.{capability}: mode={mode!r} is not in {list(allowed)}"
                )
                continue
            modes[capability] = mode
            scopes = block.get("scopes")
            if not isinstance(scopes, list):
                failures.append(f"{object_id}.{capability}: scopes must be a list")
                continue
            expected = f"assistant.{domain}.{local}.{capability}"
            if mode == "none":
                if scopes:
                    failures.append(
                        f"{object_id}.{capability}: mode=none must carry no scopes, "
                        f"found {scopes}"
                    )
            elif scopes != [expected]:
                failures.append(
                    f"{object_id}.{capability}: scopes={scopes} must be exactly "
                    f"[{expected!r}]; a capability cannot be granted under another "
                    "object's scope"
                )
            if capability != "write":
                for forbidden in ("requires_user_consent", "consent_scope_ref"):
                    if forbidden in block:
                        failures.append(
                            f"{object_id}.{capability}: {forbidden} only belongs on write"
                        )
                continue
            if mode == "none":
                for forbidden in ("requires_user_consent", "consent_scope_ref"):
                    if forbidden in block:
                        failures.append(
                            f"{object_id}.write: {forbidden} is meaningless when "
                            "write is closed"
                        )
                continue
            if block.get("requires_user_consent") is not True:
                failures.append(
                    f"{object_id}.write: mode={mode} requires "
                    "requires_user_consent: true"
                )
            if block.get("consent_scope_ref") != expected:
                failures.append(
                    f"{object_id}.write: consent_scope_ref="
                    f"{block.get('consent_scope_ref')!r} must equal {expected!r} so the "
                    "SkillConsent grant and the ApproveTool prompt name one scope"
                )
        if len(modes) != len(MODES):
            continue
        fully_closed = all(value == "none" for value in modes.values())
        reason = str(access.get("denied_reason", "")).strip()
        if fully_closed and not reason:
            failures.append(
                f"{object_id}: fully closed to the assistant must state denied_reason"
            )
        if not fully_closed and reason:
            failures.append(
                f"{object_id}: denied_reason is only valid when read, cite and write "
                "are all none"
            )
        if modes["cite"] != "none" and modes["read"] == "none":
            failures.append(
                f"{object_id}: cite={modes['cite']} without read is unreachable; "
                "the assistant cannot quote what it may not read"
            )
    return failures


# publicObjectDescriptor(descriptorID, resolverRef, ownerService,
#                        ownerOperationRef, inputSchemaRef, objectTypeRef, ...)
PUBLIC_DESCRIPTOR_OBJECT_TYPE_ARG = 5


def descriptor_object_type_refs(repo_root: Path) -> list[str]:
    """Every object type the hand-written descriptor catalogue hands the assistant.

    Only the argument position and the field that actually carry object identity
    are read. `InputSchemaRef` is also a dotted PascalCase literal, so matching by
    shape alone would drag query DTO names in and report them as missing objects.
    """
    path = repo_root / DESCRIPTORS_RELATIVE
    if not path.is_file():
        raise ScanError(f"missing descriptor catalogue: {path}")
    body = path.read_text(encoding="utf-8")
    literals: set[str] = set()

    for call in re.finditer(
        r"(?<!func )publicObjectDescriptor\(([^)]*)\)", body, re.DOTALL
    ):
        arguments = [item.strip() for item in call.group(1).split(",")]
        arguments = [item for item in arguments if item]
        if len(arguments) <= PUBLIC_DESCRIPTOR_OBJECT_TYPE_ARG:
            raise ScanError(
                f"{path}: publicObjectDescriptor call has "
                f"{len(arguments)} arguments; the object type position moved and the "
                "scan can no longer locate it"
            )
        argument = arguments[PUBLIC_DESCRIPTOR_OBJECT_TYPE_ARG]
        match = re.fullmatch(r'"([a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*)"', argument)
        if not match:
            raise ScanError(
                f"{path}: publicObjectDescriptor object type argument {argument!r} is "
                "not a literal object reference"
            )
        literals.add(match.group(1))

    # Composite literals use `ObjectTypeRefs:` and the resolver-keyed overrides
    # use `ObjectTypeRefs =`; both are authored object identity.
    for block in re.finditer(
        r"ObjectTypeRefs\s*[:=]\s*\[\]string\{([^}]*)\}", body, re.DOTALL
    ):
        literals.update(
            re.findall(r'"([a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*)"', block.group(1))
        )

    if not literals:
        raise ScanError(
            f"{path}: found no object type literals; the descriptor scan would "
            "vacuously pass"
        )
    return sorted(literals)


def validate_descriptor_derivation(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> list[str]:
    failures: list[str] = []
    for literal in descriptor_object_type_refs(repo_root):
        domain, name = literal.split(".", 1)
        object_id = f"{domain}.{pascal_to_snake(name)}"
        if object_id not in objects:
            failures.append(
                f"DomainReaderDescriptor exposes {literal!r}, which is not an object "
                "on disk; the descriptor catalogue must be derivable from the "
                "contract graph, not authored independently"
            )
            continue
        access = objects[object_id][1].get("assistant_access", {})
        mode = access.get("read", {}).get("mode")
        if mode in (None, "none"):
            failures.append(
                f"DomainReaderDescriptor exposes {literal!r} but its object declares "
                f"assistant_access.read.mode={mode!r}; a Reader cannot hand the "
                "assistant an object the contract closes"
            )
    return failures


def validate_privacy_coupling(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> list[str]:
    failures: list[str] = []
    checked = 0
    for object_id, (path, document) in sorted(objects.items()):
        privacy_path = path.parent / "privacy.yaml"
        if not privacy_path.is_file():
            continue
        checked += 1
        try:
            privacy = yaml.safe_load(privacy_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ScanError(f"{privacy_path}: {error}") from error
        if not isinstance(privacy, dict):
            raise ScanError(f"{privacy_path}: expected a mapping")
        read_mode = (
            document.get("assistant_access", {}).get("read", {}).get("mode", "none")
        )
        for entry in privacy.get("field_visibility") or []:
            if not isinstance(entry, dict):
                continue
            consumers = entry.get("visibility") or []
            if "assistant" not in consumers:
                continue
            if read_mode == "none":
                failures.append(
                    f"{object_id}: {privacy_path.name} exposes field "
                    f"{entry.get('field')!r} to the assistant consumer while "
                    "assistant_access.read.mode=none"
                )
    return failures


SEARCH_REGISTRY_RELATIVE = "quwoquan_service/contracts/metadata/_shared/search_objects.yaml"
SEARCH_ACCESS_RELATIVE = (
    "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/"
    "infrastructure/searchclient/assistant_object_access.go"
)


def expected_search_exposure(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> tuple[set[str], set[str]]:
    """Project assistant policy onto the registered search types.

    This is the rule `app_search` enforces at runtime, recomputed from the
    contracts so the Go allowlist cannot be widened on its own.
    """
    registry_path = repo_root / SEARCH_REGISTRY_RELATIVE
    if not registry_path.is_file():
        raise ScanError(f"missing search registry: {registry_path}")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    entries = (registry or {}).get("object_types") or []
    if not entries:
        raise ScanError(f"{registry_path}: 0 registered object types")
    readable: set[str] = set()
    citable: set[str] = set()
    for entry in entries:
        object_type = str(entry.get("id", "")).strip()
        owner = str(entry.get("owner_object", "")).strip()
        if owner not in objects:
            # The search-policy gate owns this failure; do not double-report.
            continue
        if str(entry.get("execution_strategy", "")).strip() == "filter_only":
            continue
        document = objects[owner][1]
        if str(entry.get("domain", "")).strip() == "external":
            policy = document.get("search_policy") or {}
            if policy.get("exposed") == "remote_provider":
                readable.add(object_type)
                citable.add(object_type)
            continue
        access = document.get("assistant_access") or {}
        if (access.get("read") or {}).get("mode") != "public":
            continue
        readable.add(object_type)
        if (access.get("cite") or {}).get("mode") not in (None, "none"):
            citable.add(object_type)
    return readable, citable


def go_literal_sets(repo_root: Path) -> dict[str, set[str]]:
    path = repo_root / SEARCH_ACCESS_RELATIVE
    if not path.is_file():
        raise ScanError(f"missing app_search allowlist: {path}")
    body = path.read_text(encoding="utf-8")
    found: dict[str, set[str]] = {}
    for name in ("assistantReadableObjectTypes", "assistantCitableObjectTypes"):
        block = re.search(
            rf"{name}\s*=\s*map\[string\]bool\{{(.*?)\n\t\}}", body, re.DOTALL
        )
        if not block:
            raise ScanError(f"{path}: {name} literal not found")
        found[name] = set(
            re.findall(r'"([a-z][a-z0-9_.]*)":\s*true', block.group(1))
        )
        if not found[name]:
            raise ScanError(f"{path}: {name} parsed as empty")
    return found


def validate_search_exposure(
    repo_root: Path, objects: dict[str, tuple[Path, dict]]
) -> list[str]:
    readable, citable = expected_search_exposure(repo_root, objects)
    literals = go_literal_sets(repo_root)
    failures: list[str] = []
    for name, expected in (
        ("assistantReadableObjectTypes", readable),
        ("assistantCitableObjectTypes", citable),
    ):
        actual = literals[name]
        for extra in sorted(actual - expected):
            failures.append(
                f"{name} allows search type {extra!r} that the owning object's "
                "assistant_access does not open; app_search would return a hit the "
                "object contract closes"
            )
        for missing in sorted(expected - actual):
            failures.append(
                f"{name} omits search type {missing!r} that the owning object opens; "
                "the allowlist must be the contract's projection, not a hand-kept "
                "subset of it"
            )
    return failures


def run(repo_root: Path) -> tuple[int, list[str]]:
    objects = load_objects(repo_root)
    failures = validate_declarations(repo_root, objects)
    failures += validate_descriptor_derivation(repo_root, objects)
    failures += validate_privacy_coupling(repo_root, objects)
    failures += validate_search_exposure(repo_root, objects)
    return len(objects), failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    arguments = parser.parse_args(argv)
    repo_root = Path(arguments.repo_root).resolve()
    try:
        scanned, failures = run(repo_root)
    except ScanError as error:
        print(f"[assistant-access] FAIL: {error}")
        return 1
    except (OSError, yaml.YAMLError) as error:
        print(f"[assistant-access] FAIL: {error}")
        return 1
    if failures:
        for failure in failures:
            print(f"[assistant-access] FAIL: {failure}")
        print(f"[assistant-access] GATE_BLOCK: {len(failures)} failure(s)")
        return 1
    print(f"[assistant-access] OK: objects={scanned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

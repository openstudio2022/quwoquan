#!/usr/bin/env python3
"""Detect drift between the three places a search field has to exist.

A searchable field only works if all three of these agree, and nothing checked
them against each other:

1. the ES mapping (`runtime/search/es/index_schema.go`) — what the index can
   actually match on;
2. the index writer (`runtime/search/es/indexer.go`) — which document keys are
   written as top-level fields versus buried in the non-indexed `payload`;
3. the owner object's `fields.yaml` — the contract that says the source field
   exists at all.

The three failure modes are genuinely different, so they are reported
separately rather than folded into one "mismatch":

* A key written as a top-level field with no mapping property gets ES dynamic
  mapping instead of the intended analyzer — it looks indexed and behaves wrong.
* A mapping property nothing writes is dead weight that later reads as evidence
  that a feature exists.
* A projector that reads a source field which `fields.yaml` no longer declares is
  a rename that silently started projecting a zero value.

The third check is why this gate reads `search_policy.index_projector_ref`
instead of scanning for projector-shaped names: the object contract already says
which function is the projector, so a renamed or relocated projector fails the
search-policy gate rather than quietly dropping out of this one.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_SCHEMA_RELATIVE = "quwoquan_service/runtime/search/es/index_schema.go"
INDEXER_RELATIVE = "quwoquan_service/runtime/search/es/indexer.go"

# `embedding` is written by the hybrid kNN path only when the deployment
# configures dense vectors, so the mapping declares it without the indexer
# writing it unconditionally.
CONFIG_GATED_PROPERTIES = frozenset({"embedding"})


class ScanError(Exception):
    """Raised when the scan itself cannot be trusted, never for a policy failure."""


def read_source(repo_root: Path, relative: str) -> str:
    path = repo_root / relative
    if not path.is_file():
        raise ScanError(f"missing source: {path}")
    return path.read_text(encoding="utf-8")


def mapping_properties(body: str) -> set[str]:
    block = re.search(
        r"func buildIndexMappings\([^)]*\)[^{]*\{(.*?)\n\}", body, re.DOTALL
    )
    if not block:
        raise ScanError("buildIndexMappings not found in index_schema.go")
    keys = set(re.findall(r'^\s*"([A-Za-z][A-Za-z0-9_]*)":\s', block.group(1), re.MULTILINE))
    keys.update(re.findall(r'props\["([A-Za-z][A-Za-z0-9_]*)"\]\s*=', block.group(1)))
    # Drop the nested option keys of a field definition ("type", "dims", ...).
    keys -= {
        "type",
        "dims",
        "index",
        "similarity",
        "analyzer",
        "search_analyzer",
        "fields",
        "kw",
        "ignore_above",
        "enabled",
        "properties",
    }
    if not keys:
        raise ScanError("buildIndexMappings yielded 0 properties")
    return keys


def indexer_written_keys(body: str) -> tuple[set[str], set[str]]:
    block = re.search(
        r"func DocumentToIndex\([^)]*\)[^{]*\{(.*?)\n\}", body, re.DOTALL
    )
    if not block:
        raise ScanError("DocumentToIndex not found in indexer.go")
    section = block.group(1)
    written = set(re.findall(r'^\s*"([A-Za-z][A-Za-z0-9_]*)":\s', section, re.MULTILINE))
    written.update(re.findall(r'out\["([A-Za-z][A-Za-z0-9_]*)"\]\s*=', section))
    anchors = re.search(r"anchorFieldKeys = \[\]string\{(.*?)\}", body, re.DOTALL)
    if not anchors:
        raise ScanError("anchorFieldKeys not found in indexer.go")
    anchor_keys = set(re.findall(r'"([A-Za-z][A-Za-z0-9_]*)"', anchors.group(1)))
    if not written or not anchor_keys:
        raise ScanError("indexer scan yielded no written keys or no anchor keys")
    return written, anchor_keys


def object_paths(repo_root: Path) -> list[Path]:
    service_root = repo_root / "quwoquan_service"
    if not service_root.is_dir():
        raise ScanError(f"service root does not exist: {service_root}")
    found = set(service_root.glob("*/*/contracts/*/*/object.yaml"))
    found |= set(service_root.glob("*/*/*/contracts/*/*/object.yaml"))
    return sorted(found)


def normalized(name: str) -> str:
    """Compare field names without the store's `_id` decoration."""
    return name.lstrip("_").lower()


def declared_field_names(object_dir: Path, document: dict) -> set[str]:
    fields_path = object_dir / "fields.yaml"
    if not fields_path.is_file():
        return set()
    text = fields_path.read_text(encoding="utf-8")
    # fields.yaml nests sub-field lists under request/response shapes, so every
    # `- name:` at any depth is a declared field of this object's contract.
    names = set(
        re.findall(r"^\s*-?\s*name:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", text, re.MULTILINE)
    ) | set(re.findall(r"\{name:\s*([A-Za-z_][A-Za-z0-9_]*)", text))
    # The identity field lives in object.yaml, not fields.yaml, but a projector
    # reading the object's own id is reading a declared contract field. Go spells
    # that field `ID` whatever the contract calls it (`_id`, `homepageId`), so a
    # bare `ID` read is checked against the declaration existing at all, not
    # against a name it was never going to match.
    identity = [
        str(value)
        for value in (document.get("identity") or {}).get("fields") or []
        if isinstance(value, (str, int))
    ]
    names.update(identity)
    if identity:
        names.add("id")
    return names


def projector_source_reads(repo_root: Path, reference: str) -> tuple[set[str], set[str]]:
    """Return (Fields map keys, source selector names) read by a projector."""
    relative, symbol = reference.rsplit("#", 1)
    body = read_source(repo_root, relative)
    match = re.search(
        rf"^func {re.escape(symbol)}\((?P<params>[^)]*)\)[^{{]*\{{(?P<body>.*?)\n\}}",
        body,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        raise ScanError(f"{reference}: projector function body not found")
    section = match.group("body")
    field_keys = set()
    fields_literal = re.search(
        r"Fields:\s*map\[string\]string\{(.*?)\n\t\t\}", section, re.DOTALL
    ) or re.search(r"fields\s*:?=\s*map\[string\]string\{(.*?)\n\t\}", section, re.DOTALL)
    if fields_literal:
        field_keys = set(
            re.findall(r'^\s*"([A-Za-z][A-Za-z0-9_]*)":', fields_literal.group(1), re.MULTILINE)
        )
    params = match.group("params").strip()
    receiver = params.split()[0].rstrip(",") if params else ""
    selectors: set[str] = set()
    if receiver:
        selectors = set(
            re.findall(rf"\b{re.escape(receiver)}\.([A-Z][A-Za-z0-9]*)\b", section)
        )
    return field_keys, selectors


def lower_camel(value: str) -> str:
    # Go exports use trailing-acronym forms (UserID, AvatarURL) that the contract
    # spells userId / avatarUrl. A name that is nothing but the acronym ("ID")
    # lowercases whole, otherwise "ID" would become "iD" and never match anything.
    for acronym in ("ID", "URL"):
        if value == acronym:
            return acronym.lower()
        if value.endswith(acronym):
            value = value[: -len(acronym)] + acronym.capitalize()
    return value[0].lower() + value[1:]


def run(repo_root: Path) -> tuple[dict[str, int], list[str]]:
    schema_body = read_source(repo_root, INDEX_SCHEMA_RELATIVE)
    indexer_body = read_source(repo_root, INDEXER_RELATIVE)
    properties = mapping_properties(schema_body)
    written, anchors = indexer_written_keys(indexer_body)

    failures: list[str] = []
    for key in sorted((written | anchors) - properties):
        failures.append(
            f"indexer writes top-level field {key!r} that the ES mapping does not "
            "declare; ES would dynamically map it instead of using the configured "
            "analyzer"
        )
    for key in sorted(properties - written - anchors - CONFIG_GATED_PROPERTIES):
        failures.append(
            f"ES mapping declares property {key!r} that no writer populates; an "
            "unwritten property is not evidence that the field is searchable"
        )

    paths = object_paths(repo_root)
    if not paths:
        raise ScanError(
            f"scanned 0 object.yaml under {repo_root / 'quwoquan_service'}; "
            "an empty scan can never be reported as a pass"
        )
    projectors = 0
    for path in paths:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ScanError(f"{path}: {error}") from error
        if not isinstance(document, dict):
            raise ScanError(f"{path}: object.yaml must be a mapping")
        policy = document.get("search_policy") or {}
        reference = str(policy.get("index_projector_ref", "")).strip()
        if "#" not in reference:
            continue
        # A projection object may point at the aggregate's projector to declare
        # that it is fed by it. Only the object that owns the indexed type can be
        # asked to declare the projector's source fields; validating the view
        # against its own fields.yaml would report the delegation seam as drift.
        if not policy.get("object_type_refs"):
            continue
        projectors += 1
        object_id = path.parents[0].name
        field_keys, selectors = projector_source_reads(repo_root, reference)
        declared = declared_field_names(path.parent, document)
        for key in sorted(field_keys & properties):
            if key not in anchors:
                failures.append(
                    f"{object_id}: projector Fields[{key!r}] collides with mapping "
                    "property but is not an anchor key, so it is written into the "
                    "non-indexed payload while the mapping implies it is searchable"
                )
        if not declared:
            failures.append(
                f"{object_id}: search_policy declares an index projector but the "
                "object has no fields.yaml to validate its source reads against"
            )
            continue
        declared_keys = {normalized(name) for name in declared}
        unknown = {
            name
            for name in selectors
            if normalized(lower_camel(name)) not in declared_keys
            and normalized(name) not in declared_keys
        }
        for name in sorted(unknown):
            failures.append(
                f"{object_id}: projector {reference.rsplit('#', 1)[1]} reads source "
                f"field {name!r} ({lower_camel(name)!r}) that fields.yaml does not "
                "declare; a renamed contract field projects a zero value silently"
            )
    counts = {
        "mapping_properties": len(properties),
        "written_keys": len(written | anchors),
        "projectors": projectors,
        "objects": len(paths),
    }
    return counts, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    arguments = parser.parse_args(argv)
    repo_root = Path(arguments.repo_root).resolve()
    try:
        counts, failures = run(repo_root)
    except ScanError as error:
        print(f"[search-index-drift] FAIL: {error}")
        return 1
    except (OSError, yaml.YAMLError) as error:
        print(f"[search-index-drift] FAIL: {error}")
        return 1
    if failures:
        for failure in failures:
            print(f"[search-index-drift] FAIL: {failure}")
        print(f"[search-index-drift] GATE_BLOCK: {len(failures)} failure(s)")
        return 1
    print(
        "[search-index-drift] OK: "
        + " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

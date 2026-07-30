#!/usr/bin/env python3
"""从 canonical Gamma manifest 投影全部 ``*.gamma-curated.json`` 场景。

默认只检查派生产物；只有显式 ``--write`` 才会在全部输入验证通过后原子替换。
该工具不写 manifest、不装配环境媒体，也不承担 Gamma runtime seed。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_service").is_dir() and (parent / "quwoquan_ops").is_dir()
)
MANIFEST_RELATIVE_PATH = Path(
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/"
    "app_gamma_seed_manifest.json"
)
CURATED_SUFFIX = ".gamma-curated.json"
EXPECTED_DERIVED_DOMAINS = {"content", "circle", "chat", "user", "entity"}

_CONTRACT_DIR = ROOT / "quwoquan_service" / "scripts" / "contract"
if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))
from verify_content_fixture_comment_counts import (  # noqa: E402
    realign_payload_counts,
)


@dataclass(frozen=True)
class ProjectionSpec:
    domain: str
    source: Path
    destination: Path
    refs: tuple[str, ...]
    curation: dict[str, Any]


@dataclass(frozen=True)
class ProjectionOutput:
    spec: ProjectionSpec
    raw: bytes


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _render_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def _required_strings(mapping: dict[str, Any], key: str, *, owner: str) -> tuple[str, ...]:
    values = mapping.get(key)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{owner}.{key} must be a non-empty string list")
    normalized = tuple(str(value).strip() for value in values)
    if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError(f"{owner}.{key} contains blank or duplicate values")
    return normalized


def _source_path(destination: Path) -> Path:
    text = str(destination)
    if not text.endswith(CURATED_SUFFIX):
        raise ValueError(f"not a curated destination: {destination}")
    return Path(text[: -len(CURATED_SUFFIX)] + ".json")


def load_projection_specs(*, root: Path = ROOT) -> tuple[ProjectionSpec, ...]:
    manifest_path = root / MANIFEST_RELATIVE_PATH
    manifest = _read_json(manifest_path)
    if manifest.get("environment") != "gamma":
        raise ValueError(f"manifest environment must be gamma: {manifest_path}")
    seed_refs = manifest.get("seedRefs")
    if not isinstance(seed_refs, list):
        raise ValueError(f"manifest seedRefs must be a list: {manifest_path}")

    specs: list[ProjectionSpec] = []
    for entry in seed_refs:
        if not isinstance(entry, dict):
            raise ValueError("manifest seedRefs entries must be objects")
        fixture_path = str(entry.get("fixturePath") or "").strip()
        if not fixture_path.endswith(CURATED_SUFFIX):
            continue
        domain = str(entry.get("domain") or "").strip()
        refs = _required_strings(entry, "refs", owner=f"seedRefs[{domain}]")
        curation = entry.get("curation")
        if not isinstance(curation, dict) or not curation:
            raise ValueError(f"seedRefs[{domain}].curation is required")
        destination = Path(fixture_path)
        source = _source_path(destination)
        if not (root / source).is_file():
            raise ValueError(f"canonical scenario source is missing: {source}")
        specs.append(
            ProjectionSpec(
                domain=domain,
                source=source,
                destination=destination,
                refs=refs,
                curation=copy.deepcopy(curation),
            )
        )

    domains = {spec.domain for spec in specs}
    if domains != EXPECTED_DERIVED_DOMAINS:
        raise ValueError(
            "Gamma derived-domain set drifted: "
            f"actual={sorted(domains)} expected={sorted(EXPECTED_DERIVED_DOMAINS)}"
        )
    destinations = [spec.destination for spec in specs]
    if len(destinations) != len(set(destinations)):
        raise ValueError("Gamma manifest declares duplicate curated destinations")
    return tuple(specs)


def _row_id(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _filter_rows(
    rows: Any,
    requested: set[str],
    *,
    keys: tuple[str, ...],
    owner: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{owner} must be a list")
    typed_rows = [row for row in rows if isinstance(row, dict)]
    present = {_row_id(row, *keys) for row in typed_rows}
    missing = sorted(requested - present)
    if missing:
        raise ValueError(f"{owner} misses curated ids: {missing}")
    return [row for row in typed_rows if _row_id(row, *keys) in requested]


def _curation_sets(
    specs: tuple[ProjectionSpec, ...], *, root: Path
) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = {}
    required = {
        "content": ("postIds", "excludedObjectIntersectionIds"),
        "circle": ("circleIds",),
        "chat": ("conversationIds", "contactUserIds"),
        "user": ("userIds",),
        "entity": ("homepageIds", "pickerHomepageIds"),
    }
    for spec in specs:
        result[spec.domain] = {
            key: set(
                _required_strings(
                    spec.curation,
                    key,
                    owner=f"seedRefs[{spec.domain}].curation",
                )
            )
            for key in required[spec.domain]
        }
    content_spec = next(spec for spec in specs if spec.domain == "content")
    content_source = _read_json(root / content_spec.source)
    discovery = (content_source.get("seedSets") or {}).get("content_discovery_core") or {}
    post_ids = result["content"]["postIds"]
    result["content"]["commentIds"] = {
        _row_id(row, "commentId")
        for row in discovery.get("comments", [])
        if isinstance(row, dict)
        and _row_id(row, "postId") in post_ids
        and _row_id(row, "commentId")
    }
    return result


def _prune_content(payload: dict[str, Any], selections: dict[str, set[str]]) -> None:
    seed_sets = payload["seedSets"]
    post_ids = selections["postIds"]
    comment_ids = selections["commentIds"]
    seed = seed_sets["content_discovery_core"]
    seed["posts"] = _filter_rows(
        seed.get("posts"), post_ids, keys=("postId",), owner="content.posts"
    )
    seed["reactions"] = [
        row
        for row in seed.get("reactions", [])
        if isinstance(row, dict) and _row_id(row, "postId") in post_ids
    ]
    comments = seed.get("comments")
    if not isinstance(comments, list):
        raise ValueError("content.comments must be a list")
    present_comment_ids = {
        _row_id(row, "commentId") for row in comments if isinstance(row, dict)
    }
    missing_comments = sorted(comment_ids - present_comment_ids)
    if missing_comments:
        raise ValueError(f"content.comments misses curated ids: {missing_comments}")
    seed["comments"] = [
        row
        for row in comments
        if isinstance(row, dict)
        and (
            _row_id(row, "commentId") in comment_ids
            or _row_id(row, "postId") in post_ids
        )
    ]
    intersection_seed = seed_sets.get("intersection_core")
    if isinstance(intersection_seed, dict):
        object_intersections = intersection_seed.get("objectIntersections")
        if isinstance(object_intersections, dict):
            excluded = selections["excludedObjectIntersectionIds"]
            intersection_seed["objectIntersections"] = {
                key: value
                for key, value in object_intersections.items()
                if key not in excluded
            }
    realign_payload_counts(payload)


def _prune_user(
    payload: dict[str, Any],
    selections: dict[str, set[str]],
    all_selections: dict[str, dict[str, set[str]]],
) -> None:
    seed_sets = payload["seedSets"]
    user_ids = selections["userIds"]
    profiles = seed_sets["user_profile_core"]
    profiles["profiles"] = _filter_rows(
        profiles.get("profiles"), user_ids, keys=("userId",), owner="user.profiles"
    )
    feed = seed_sets["profile_feed_core"]
    post_ids = all_selections["content"]["postIds"]
    comment_ids = all_selections["content"]["commentIds"]
    feed["myPostIds"] = [value for value in feed.get("myPostIds", []) if value in post_ids]
    feed["authorPostIds"] = [
        value for value in feed.get("authorPostIds", []) if value in post_ids
    ]
    feed["commentIds"] = [
        value for value in feed.get("commentIds", []) if value in comment_ids
    ]
    relationships = seed_sets["relationship_core"]
    relationships["relationships"] = [
        row
        for row in relationships.get("relationships", [])
        if isinstance(row, dict)
        and _row_id(row, "sourceUserId") in user_ids
        and _row_id(row, "targetUserId") in user_ids
    ]


def _prune_circle(payload: dict[str, Any], selections: dict[str, set[str]]) -> None:
    seed_sets = payload["seedSets"]
    circle_ids = selections["circleIds"]
    core = seed_sets["circle_core"]
    core["circles"] = _filter_rows(
        core.get("circles"), circle_ids, keys=("id",), owner="circle.circles"
    )
    for key in ("groups", "members", "files"):
        mapping = core.get(key)
        if not isinstance(mapping, dict):
            raise ValueError(f"circle.{key} must be an object")
        core[key] = {
            item_key: value for item_key, value in mapping.items() if item_key in circle_ids
        }
    links = seed_sets["circle_group_chat_link_core"]
    links["links"] = [
        row
        for row in links.get("links", [])
        if isinstance(row, dict) and _row_id(row, "circleId") in circle_ids
    ]


def _prune_chat(
    payload: dict[str, Any],
    selections: dict[str, set[str]],
    all_selections: dict[str, dict[str, set[str]]],
) -> None:
    seed_sets = payload["seedSets"]
    conversation_ids = selections["conversationIds"]
    contact_ids = selections["contactUserIds"]
    core = seed_sets["chat_core"]
    core["conversations"] = _filter_rows(
        core.get("conversations"),
        conversation_ids,
        keys=("id",),
        owner="chat.conversations",
    )
    for key in ("members", "messages"):
        mapping = core.get(key)
        if not isinstance(mapping, dict):
            raise ValueError(f"chat.{key} must be an object")
        core[key] = {
            item_key: value
            for item_key, value in mapping.items()
            if item_key in conversation_ids
        }
    core["userStates"] = [
        row
        for row in core.get("userStates", [])
        if isinstance(row, dict)
        and _row_id(row, "conversationId") in conversation_ids
    ]
    contacts = seed_sets["chat_contacts_core"]
    contacts["contacts"] = _filter_rows(
        contacts.get("contacts"), contact_ids, keys=("userId",), owner="chat.contacts"
    )
    circle_ids = all_selections["circle"]["circleIds"]
    contacts["circleIds"] = [
        value for value in contacts.get("circleIds", []) if value in circle_ids
    ]
    contacts["groupConversationIds"] = [
        value
        for value in contacts.get("groupConversationIds", [])
        if value in conversation_ids
    ]
    group_flow = seed_sets["chat_group_flow_core"]
    group_flow["candidateUserIds"] = [
        value
        for value in group_flow.get("candidateUserIds", [])
        if value in contact_ids
    ]


def _prune_entity(payload: dict[str, Any], selections: dict[str, set[str]]) -> None:
    seed_sets = payload["seedSets"]
    homepage_ids = selections["homepageIds"]
    picker_ids = selections["pickerHomepageIds"]
    if not picker_ids <= homepage_ids:
        raise ValueError("entity pickerHomepageIds must be a subset of homepageIds")
    core = seed_sets["entity_homepage_core"]
    core["homepages"] = _filter_rows(
        core.get("homepages"),
        homepage_ids,
        keys=("homepageId",),
        owner="entity.homepages",
    )
    homepage_by_id = {
        _row_id(row, "homepageId"): row for row in core["homepages"]
    }
    claims = seed_sets["entity_claim_core"]
    claims["claims"] = [
        row
        for row in claims.get("claims", [])
        if isinstance(row, dict) and _row_id(row, "homepageId") in homepage_ids
    ]
    picker = seed_sets["entity_picker_core"]
    ordered_picker_ids = [
        value
        for value in picker.get("candidateHomepageIds", [])
        if value in picker_ids
    ]
    if set(ordered_picker_ids) != picker_ids:
        raise ValueError("entity picker source misses curated homepage ids")
    picker["candidateHomepageIds"] = ordered_picker_ids
    claim_ids = [
        _row_id(row, "claimId") for row in claims["claims"] if _row_id(row, "claimId")
    ]
    titles = [str(homepage_by_id[value].get("title") or "").strip() for value in ordered_picker_ids]
    if any(not title for title in titles):
        raise ValueError("entity curated picker homepages must all have titles")
    for scenario in payload.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        ui = scenario.get("uiExpectations")
        if isinstance(ui, dict):
            ui["homepageIds"] = ordered_picker_ids
            ui["textFragments"] = titles
        remote = scenario.get("remoteExpectations")
        if isinstance(remote, dict):
            remote["homepageIds"] = ordered_picker_ids
            remote["claimIds"] = claim_ids


def _build_payload(
    spec: ProjectionSpec,
    *,
    root: Path,
    all_selections: dict[str, dict[str, set[str]]],
) -> dict[str, Any]:
    source = _read_json(root / spec.source)
    seed_sets = source.get("seedSets")
    if not isinstance(seed_sets, dict):
        raise ValueError(f"{spec.source} seedSets must be an object")
    missing_refs = sorted(set(spec.refs) - set(seed_sets))
    if missing_refs:
        raise ValueError(f"{spec.source} misses manifest refs: {missing_refs}")
    payload = copy.deepcopy(source)
    payload["description"] = (
        str(source.get("description") or "").strip() + " [gamma-curated subset]"
    ).strip()
    payload["seedSets"] = {
        ref: copy.deepcopy(seed_sets[ref]) for ref in spec.refs
    }
    scenarios: list[dict[str, Any]] = []
    for item in source.get("scenarios", []):
        if not isinstance(item, dict):
            continue
        next_item = copy.deepcopy(item)
        next_item["seedRefs"] = [
            ref for ref in item.get("seedRefs", []) if ref in spec.refs
        ]
        scenarios.append(next_item)
    payload["scenarios"] = scenarios

    selections = all_selections[spec.domain]
    if spec.domain == "content":
        _prune_content(payload, selections)
    elif spec.domain == "user":
        _prune_user(payload, selections, all_selections)
    elif spec.domain == "circle":
        _prune_circle(payload, selections)
    elif spec.domain == "chat":
        _prune_chat(payload, selections, all_selections)
    elif spec.domain == "entity":
        _prune_entity(payload, selections)
    else:  # guarded by EXPECTED_DERIVED_DOMAINS
        raise ValueError(f"unsupported Gamma curated domain: {spec.domain}")
    return payload


def build_projection_outputs(*, root: Path = ROOT) -> tuple[ProjectionOutput, ...]:
    specs = load_projection_specs(root=root)
    all_selections = _curation_sets(specs, root=root)
    return tuple(
        ProjectionOutput(
            spec=spec,
            raw=_render_json(
                _build_payload(spec, root=root, all_selections=all_selections)
            ),
        )
        for spec in specs
    )


def stale_destinations(
    outputs: tuple[ProjectionOutput, ...], *, root: Path = ROOT
) -> tuple[Path, ...]:
    stale: list[Path] = []
    for output in outputs:
        destination = root / output.spec.destination
        if not destination.is_file() or destination.read_bytes() != output.raw:
            stale.append(output.spec.destination)
    return tuple(stale)


def _atomic_write_all(
    outputs: tuple[ProjectionOutput, ...], *, root: Path = ROOT
) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for output in outputs:
            destination = root / output.spec.destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(output.raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
            staged.append((temporary, destination))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查；这是默认模式。")
    mode.add_argument("--write", action="store_true", help="显式原子更新全部派生场景。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = build_projection_outputs()
    stale = stale_destinations(outputs)
    if args.write:
        _atomic_write_all(outputs)
        stale = stale_destinations(outputs)
    status = "ok" if not stale else "stale"
    print(
        json.dumps(
            {
                "status": status,
                "mode": "write" if args.write else "check",
                "manifest": str(MANIFEST_RELATIVE_PATH),
                "derivedDomains": [output.spec.domain for output in outputs],
                "outputs": [str(output.spec.destination) for output in outputs],
                "stale": [str(path) for path in stale],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not stale else 1


if __name__ == "__main__":
    raise SystemExit(main())

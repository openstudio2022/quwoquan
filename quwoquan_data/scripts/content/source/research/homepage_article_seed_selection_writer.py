"""Create exact acquisition seeds from legacy hints or one current coverage run."""

from __future__ import annotations

import argparse
import json
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from governance.coverage.coverage_source_ready_catalog_projection import (
    project_coverage_source_ready_catalog_inputs,
)

from content.source.research.homepage_article_seed_selection import (
    HomepageArticleSeedSelectionError,
    load_homepage_article_seed_selection,
    seed_id,
)
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    file_sha256,
    write_create_once_json,
)
from content.source.research.scale_source_pool_evidence_path import (
    ScaleSourcePoolEvidencePathError,
    compute_evidence_file_sha256,
    resolve_evidence_file,
    resolve_evidence_root,
)


def _fail(issue: str) -> None:
    raise HomepageArticleSeedSelectionError([issue])


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"{label} is not readable JSON: {exc}")
    if not isinstance(value, dict):
        _fail(f"{label} must be one JSON object")
    return value


def _historical_inputs(
    *, evidence_root: Path, batch_refs: Sequence[str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    bindings: dict[str, dict[str, Any]] = {}
    planned: list[dict[str, Any]] = []
    seen_projection_digests: set[str] = set()
    for index, ref in enumerate(batch_refs):
        batch_path = resolve_evidence_file(
            evidence_root, ref, label=f"historicalBatchRefs[{index}]"
        )
        batch = _object(batch_path, label=f"historical batch {ref}")
        if batch.get("schema") != "quwoquan_data.homepage_article_source_ready_batch":
            _fail(f"historical batch schema is invalid: {ref}")
        for raw in batch.get("candidateCapsules") or []:
            if not isinstance(raw, Mapping):
                _fail(f"historical candidate binding is invalid: {ref}")
            candidate_id = str(raw.get("candidateId") or "")
            if not candidate_id or candidate_id in bindings:
                _fail(f"duplicate or empty historical candidateId: {candidate_id}")
            bindings[candidate_id] = dict(raw)
        projection_binding = batch.get("coverageProjection")
        if not isinstance(projection_binding, Mapping):
            _fail(f"historical coverage projection binding is missing: {ref}")
        projection_digest = str(projection_binding.get("digest") or "")
        if projection_digest in seen_projection_digests:
            continue
        projection_path = resolve_evidence_file(
            evidence_root,
            projection_binding.get("ref"),
            label=f"historicalBatchRefs[{index}].coverageProjection",
        )
        if (
            compute_evidence_file_sha256(projection_path)
            != projection_binding.get("fileSha256")
        ):
            _fail(f"historical coverage projection file drift: {ref}")
        projection = _object(projection_path, label=f"coverage projection {ref}")
        stable = {
            key: value
            for key, value in projection.items()
            if key != "projectionDigest"
        }
        if projection.get("projectionDigest") != canonical_digest(stable):
            _fail(f"historical coverage projection digest drift: {ref}")
        rows = projection.get("plannedCandidates")
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            _fail(f"historical coverage projection candidates are invalid: {ref}")
        planned.extend(dict(row) for row in rows)
        seen_projection_digests.add(projection_digest)
    return bindings, planned


def _entity_ref(row: Mapping[str, Any]) -> str:
    canonical = str(row.get("canonicalEntityRef") or "")
    if canonical:
        return canonical
    entity_type = str(row.get("entityType") or "")
    name = str(row.get("candidateName") or "")
    return f"/entity/{entity_type}/{name}"


def _coverage_identity(row: Mapping[str, Any]) -> str:
    observed = str(row.get("coverageEntityIdentity") or "").strip()
    if observed:
        return observed
    return "name_location:{name}|{province}|{city}|{district}".format(
        name=str(row.get("candidateName") or ""),
        province=str(row.get("province") or ""),
        city=str(row.get("city") or ""),
        district=str(row.get("district") or ""),
    )


def _seed_from_coverage_row(
    row: Mapping[str, Any],
    *,
    carrier: str,
    seed_origin: str,
    entity_ref: str,
    historical_baseline: Mapping[str, Any] | None = None,
    article_category: str = "",
) -> dict[str, Any]:
    source = row.get("source")
    source = source if isinstance(source, Mapping) else {}
    coverage_key = {
        "coverageEntityIdentity": _coverage_identity(row),
        "coverageRecordDigest": str(
            row.get("coverageRecordDigest") or canonical_digest(dict(row))
        ),
        "entityRef": entity_ref,
        "carrier": carrier,
        "sourceUrl": str(source.get("sourceUrl") or ""),
    }
    seed: dict[str, Any] = {
        "seedOrigin": seed_origin,
        "seedId": seed_id(
            seed_origin=seed_origin,
            coverage_key=coverage_key,
            article_category=article_category,
        ),
        "coverageKey": coverage_key,
        "candidateName": str(row.get("candidateName") or ""),
        "province": str(row.get("province") or ""),
        "city": str(row.get("city") or ""),
        "district": str(row.get("district") or ""),
        "entityType": str(row.get("entityType") or ""),
        "sourceKind": str(source.get("sourceKind") or ""),
        "extractor": str(source.get("extractor") or ""),
    }
    if article_category:
        if carrier != "article" or article_category != "photography":
            _fail("article category seed must be the governed photography profile")
        seed.update(
            {
                "articleCategory": "photography",
                "writingIntent": "planning_consultation",
                "topicTagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            }
        )
    if historical_baseline is not None:
        seed["historicalBaseline"] = dict(historical_baseline)
    return seed


def _selection(*, seed_set_id: str, seeds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [dict(row) for row in seeds]
    normalized.sort(
        key=lambda row: (
            0 if row["coverageKey"]["carrier"] == "homepage" else 1,
            row["coverageKey"]["entityRef"],
            row["coverageKey"]["sourceUrl"],
            row["seedId"],
        )
    )
    stable = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": seed_set_id,
        "counts": {
            carrier: sum(
                row["coverageKey"]["carrier"] == carrier for row in normalized
            )
            for carrier in ("homepage", "article")
        },
        "seeds": normalized,
    }
    result = {**stable, "selectionDigest": canonical_digest(stable)}
    try:
        assert_valid(
            result,
            "source",
            "homepage_article_seed_selection",
            label="homepage/article seed selection",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise HomepageArticleSeedSelectionError([str(exc)]) from exc
    return result


def _ndjson_objects(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise OSError("not a regular non-symlink file")
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise TypeError(f"row {line_number} is not an object")
                rows.append(row)
        return rows
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        _fail(f"{label} is invalid: {exc}")


def _indexed_rows(
    rows: Sequence[Mapping[str, Any]], *, label: str
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = str(row.get("identityKey") or "")
        if not identity or identity in indexed:
            _fail(f"{label} contains duplicate or empty identityKey: {identity}")
        indexed[identity] = dict(row)
    return indexed


def build_seed_selection_from_current_coverage(
    *,
    coverage_run_dir: Path,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    seed_set_id: str,
    homepage_entity_refs: Sequence[str],
    article_entity_refs: Sequence[str],
    article_photography_entity_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Select explicit current ready+frozen entities without historical capsules."""

    root = coverage_run_dir.expanduser().absolute()
    try:
        initial = project_coverage_source_ready_catalog_inputs(
            run_dir=root,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSeedSelectionError(
            [f"current coverage evidence is invalid: {exc}"]
        ) from exc
    requested = [
        *(("homepage", str(entity_ref), "") for entity_ref in homepage_entity_refs),
        *(("article", str(entity_ref), "") for entity_ref in article_entity_refs),
        *(
            ("article", str(entity_ref), "photography")
            for entity_ref in article_photography_entity_refs
        ),
    ]
    if not requested:
        _fail("at least one homepage/article current entityRef is required")
    carrier_refs = [(carrier, entity_ref) for carrier, entity_ref, _ in requested]
    if len(carrier_refs) != len(set(carrier_refs)):
        _fail("current coverage carrier+entityRef requests must be unique")
    if any(
        re.fullmatch(r"/entity/[^/]+/[^/]+/[^/]+", entity_ref) is None
        for _, entity_ref, _ in requested
    ):
        _fail("current coverage entityRef is invalid")
    planned = [
        dict(row)
        for row in initial.get("plannedCandidates") or []
        if isinstance(row, Mapping)
    ]
    by_ref: dict[str, list[dict[str, Any]]] = {}
    for row in planned:
        canonical_ref = str(row.get("canonicalEntityRef") or "")
        if not canonical_ref:
            _fail("current coverage projection lacks canonicalEntityRef")
        by_ref.setdefault(canonical_ref, []).append(row)
    ready = _indexed_rows(
        _ndjson_objects(root / "source_ready.ndjson", label="source_ready.ndjson"),
        label="source_ready.ndjson",
    )
    frozen = _indexed_rows(
        _ndjson_objects(root / "frozen_targets.ndjson", label="frozen_targets.ndjson"),
        label="frozen_targets.ndjson",
    )
    seeds: list[dict[str, Any]] = []
    for carrier, entity_ref, article_category in requested:
        matches = by_ref.get(entity_ref) or []
        if len(matches) != 1:
            qualifier = "missing" if not matches else "ambiguous"
            _fail(f"current coverage entityRef is {qualifier}: {entity_ref}")
        row = matches[0]
        identity = str(row["coverageEntityIdentity"])
        ready_row = ready.get(identity)
        frozen_row = frozen.get(identity)
        if ready_row is None or frozen_row is None:
            _fail(f"current coverage entity is not ready+frozen: {entity_ref}")
        frozen_ready = {key: value for key, value in frozen_row.items() if key != "selection"}
        if frozen_ready != ready_row:
            _fail(f"current coverage ready/frozen membership drift: {entity_ref}")
        if row.get("coverageRecordDigest") != canonical_digest(frozen_row):
            _fail(f"current coverage record digest drift: {entity_ref}")
        seeds.append(
            _seed_from_coverage_row(
                row,
                carrier=carrier,
                seed_origin="current_coverage",
                entity_ref=entity_ref,
                article_category=article_category,
            )
        )
    try:
        observed = project_coverage_source_ready_catalog_inputs(
            run_dir=root,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSeedSelectionError(
            [f"current coverage evidence changed or became invalid: {exc}"]
        ) from exc
    if observed != initial:
        _fail("current coverage evidence changed during seed selection")
    return _selection(seed_set_id=seed_set_id, seeds=seeds)


def build_seed_selection_from_historical_capsules(
    *,
    evidence_root: Path,
    batch_refs: Sequence[str],
    seed_set_id: str,
    homepage_candidate_ids: Sequence[str],
    article_candidate_ids: Sequence[str],
) -> dict[str, Any]:
    """Strip legacy identity/receipt fields and retain only fresh lookup hints."""

    root = resolve_evidence_root(evidence_root)
    bindings, planned = _historical_inputs(
        evidence_root=root, batch_refs=tuple(batch_refs)
    )
    coverage: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in planned:
        key = (
            _entity_ref(row),
            str((row.get("source") or {}).get("sourceUrl") or ""),
        )
        coverage.setdefault(key, []).append(row)
    requested = [
        (carrier, candidate_id)
        for carrier, values in (
            ("homepage", homepage_candidate_ids),
            ("article", article_candidate_ids),
        )
        for candidate_id in values
    ]
    if not requested:
        _fail("at least one homepage/article historical candidateId is required")
    if len(requested) != len({candidate_id for _, candidate_id in requested}):
        _fail("historical candidateIds must be unique")
    seeds: list[dict[str, Any]] = []
    for carrier, candidate_id in requested:
        binding = bindings.get(candidate_id)
        if binding is None or binding.get("carrier") != carrier:
            _fail(f"historical candidate binding is missing or carrier drifted: {candidate_id}")
        capsule_path = resolve_evidence_file(
            root, binding.get("ref"), label=f"historical candidate {candidate_id}"
        )
        if compute_evidence_file_sha256(capsule_path) != binding.get("fileSha256"):
            _fail(f"historical candidate file drift: {candidate_id}")
        capsule = _object(capsule_path, label=f"historical capsule {candidate_id}")
        stable = {key: value for key, value in capsule.items() if key != "capsuleDigest"}
        if (
            capsule.get("capsuleDigest") != binding.get("digest")
            or capsule.get("capsuleDigest") != canonical_digest(stable)
        ):
            _fail(f"historical candidate digest drift: {candidate_id}")
        candidate = capsule.get("candidate")
        candidate = candidate if isinstance(candidate, Mapping) else {}
        source = candidate.get("primarySource")
        source = source if isinstance(source, Mapping) else candidate
        entity_ref = str(candidate.get("entityRef") or "")
        source_url = str(source.get("sourceUrl") or "")
        matches = coverage.get((entity_ref, source_url)) or []
        if len(matches) != 1:
            _fail(f"historical coverage lookup is missing: {candidate_id}")
        row = matches[0]
        body = capsule.get("materialization")
        body = body.get("body") if isinstance(body, Mapping) else {}
        body = body if isinstance(body, Mapping) else {}
        seeds.append(
            _seed_from_coverage_row(
                row,
                carrier=carrier,
                seed_origin="legacy_hint",
                entity_ref=entity_ref,
                historical_baseline={
                    "candidateId": candidate_id,
                    "bodyContentSha256": str(body.get("contentSha256") or ""),
                },
            )
        )
    return _selection(seed_set_id=seed_set_id, seeds=seeds)


def handle_prepare_seed_selection(args: argparse.Namespace) -> None:
    try:
        current_values = (
            args.coverage_run_dir,
            args.source_revision,
            args.source_digest,
            args.entity_catalog_digest,
            *(args.homepage_entity_ref or ()),
            *(args.article_entity_ref or ()),
            *(args.article_photography_entity_ref or ()),
        )
        historical_values = (
            args.historical_evidence_root,
            *(args.historical_batch_ref or ()),
            *(args.homepage_candidate_id or ()),
            *(args.article_candidate_id or ()),
        )
        if any(current_values) and any(historical_values):
            _fail("current coverage and historical seed modes are mutually exclusive")
        if any(current_values):
            if not all(
                (
                    args.coverage_run_dir,
                    args.source_revision,
                    args.source_digest,
                    args.entity_catalog_digest,
                )
            ):
                _fail("current coverage mode requires the exact identity tuple")
            selection = build_seed_selection_from_current_coverage(
                coverage_run_dir=Path(args.coverage_run_dir),
                source_revision=args.source_revision,
                source_digest=args.source_digest,
                entity_catalog_digest=args.entity_catalog_digest,
                seed_set_id=args.seed_set_id,
                homepage_entity_refs=tuple(args.homepage_entity_ref or ()),
                article_entity_refs=tuple(args.article_entity_ref or ()),
                article_photography_entity_refs=tuple(
                    args.article_photography_entity_ref or ()
                ),
            )
        else:
            if not args.historical_evidence_root or not args.historical_batch_ref:
                _fail(
                    "legacy mode requires --historical-evidence-root and --historical-batch-ref"
                )
            selection = build_seed_selection_from_historical_capsules(
                evidence_root=Path(args.historical_evidence_root),
                batch_refs=tuple(args.historical_batch_ref),
                seed_set_id=args.seed_set_id,
                homepage_candidate_ids=tuple(args.homepage_candidate_id or ()),
                article_candidate_ids=tuple(args.article_candidate_id or ()),
            )
        destination = Path(args.output).expanduser().absolute()
        write_create_once_json(destination, selection)
        load_homepage_article_seed_selection(destination)
    except (
        FileNotFoundError,
        OSError,
        ScaleSourcePoolEvidencePathError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[source-pool prepare-homepage-article-seeds] GATE_BLOCK {exc}") from exc
    print(
        __import__("json").dumps(
            {
                "schema": "quwoquan_data.homepage_article_seed_selection_write_result",
                "selectionRef": str(destination),
                "selectionFileSha256": file_sha256(destination),
                "selectionDigest": selection["selectionDigest"],
                "counts": selection["counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def register_seed_selection_parser(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser(
        "prepare-homepage-article-seeds",
        help="从显式 current coverage 或 legacy capsule 生成 exact acquisition seeds",
    )
    parser.add_argument("--historical-evidence-root")
    parser.add_argument("--historical-batch-ref", action="append")
    parser.add_argument("--seed-set-id", required=True)
    parser.add_argument("--homepage-candidate-id", action="append")
    parser.add_argument("--article-candidate-id", action="append")
    parser.add_argument("--coverage-run-dir")
    parser.add_argument("--source-revision")
    parser.add_argument("--source-digest")
    parser.add_argument("--entity-catalog-digest")
    parser.add_argument("--homepage-entity-ref", action="append")
    parser.add_argument("--article-entity-ref", action="append")
    parser.add_argument(
        "--article-photography-entity-ref",
        action="append",
        help="显式冻结为摄影 Article 来源分类的 exact canonical entityRef",
    )
    parser.add_argument("--output", required=True)
    parser.set_defaults(handler=handle_prepare_seed_selection)


__all__ = [
    "build_seed_selection_from_historical_capsules",
    "build_seed_selection_from_current_coverage",
    "handle_prepare_seed_selection",
    "register_seed_selection_parser",
]

"""CLI-first binding for offline four-carrier source-ready pools."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT

from content.source.professional_image_discovery_governed import (
    build_professional_image_governed_candidate_catalog,
    write_professional_image_governed_candidate_catalog,
)
from content.source.research.homepage_article_source_ready_batch import (
    freeze_homepage_article_source_ready_batch,
)
from content.source.research.scale_source_pool import (
    SOURCE_POOL_INVALID,
    ScaleSourcePoolError,
    build_scale_source_pool_plan,
    validate_scale_source_pool,
    validate_scale_source_pool_evidence,
    write_create_once_scale_source_pool,
)
from content.source.research.scale_source_pool_candidates import (
    build_scale_source_pool_candidates,
    validate_scale_source_pool_candidates,
    write_create_once_scale_source_pool_candidates,
)
from content.source.research.scale_source_pool_homepage_article import (
    project_scale_source_pool_homepage_article,
)
from content.source.research.scale_source_pool_image_video import (
    project_scale_source_pool_image_video,
)


def _typed_error(error: Exception) -> ScaleSourcePoolError:
    if isinstance(error, ScaleSourcePoolError):
        return error
    code = str(getattr(error, "code", "") or "").strip()
    raw_issues = getattr(error, "issues", None)
    if code and isinstance(raw_issues, tuple | list):
        return ScaleSourcePoolError(code, raw_issues)
    issue = str(getattr(error, "issue", "") or "").strip()
    if code and issue:
        return ScaleSourcePoolError(code, [issue])
    return ScaleSourcePoolError(SOURCE_POOL_INVALID, [str(error)])


def _load_object(path: str, *, label: str) -> dict[str, Any]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _typed_error(exc) from exc
    if not isinstance(payload, dict):
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [f"{label} must be an object"])
    return payload


def _load_candidates(path: str) -> list[Mapping[str, Any]]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _typed_error(exc) from exc
    if (
        isinstance(payload, dict)
        and payload.get("schema") == "quwoquan_data.scale_source_pool_candidates"
    ):
        payload = validate_scale_source_pool_candidates(payload)
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list) or any(
        not isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["candidates input must be an array of objects"],
        )
    return candidates


def _load_array(path: str, *, label: str) -> list[Mapping[str, Any]]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _typed_error(exc) from exc
    if not isinstance(payload, list) or any(not isinstance(row, Mapping) for row in payload):
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [f"{label} must be an array of objects"])
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_destination(
    plan: Mapping[str, Any],
    *,
    output_root: Path,
) -> Path:
    target_scale = str(plan.get("targetScale") or "").strip().lower()
    digest = str(plan.get("planDigest") or "").removeprefix("sha256:")
    if not target_scale or len(digest) != 64:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["targetScale/planDigest cannot derive canonical pool path"],
        )
    return output_root / "scale-source-pools" / target_scale / f"{digest}.json"


def _canonical_candidates_destination(
    candidates: Mapping[str, Any],
    *,
    output_root: Path,
) -> Path:
    target_scale = str(candidates.get("targetScale") or "").strip().lower()
    digest = str(candidates.get("candidatesDigest") or "").removeprefix("sha256:")
    if not target_scale or len(digest) != 64:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["targetScale/candidatesDigest cannot derive canonical candidate path"],
        )
    return (
        output_root
        / "scale-source-pool-candidates"
        / target_scale
        / f"{digest}.json"
    )


def _print(document: Mapping[str, Any]) -> None:
    print(json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True))


def handle_plan(args: argparse.Namespace) -> None:
    try:
        plan = build_scale_source_pool_plan(
            pool_id=args.pool_id,
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            created_at=args.created_at,
            candidates=_load_candidates(args.candidates),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[source-pool plan] GATE_BLOCK {_typed_error(exc)}") from exc
    _print(plan)


def handle_validate(args: argparse.Namespace) -> None:
    try:
        validation = validate_scale_source_pool_evidence(
            _load_object(args.plan, label="plan"),
            evidence_root=Path(args.evidence_root),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool validate] GATE_BLOCK {_typed_error(exc)}"
        ) from exc
    _print(validation)


def handle_write(args: argparse.Namespace) -> None:
    try:
        plan = _load_object(args.plan, label="plan")
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        destination = _canonical_destination(plan, output_root=output_root)
        frozen = write_create_once_scale_source_pool(
            destination,
            plan,
            evidence_root=Path(args.evidence_root),
        )
        validation = validate_scale_source_pool(frozen)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[source-pool write] GATE_BLOCK {_typed_error(exc)}") from exc
    _print(
        {
            "schema": "quwoquan_data.scale_source_pool_write_result",
            "planRef": destination.relative_to(output_root).as_posix(),
            "planDigest": frozen["planDigest"],
            "decision": validation["decision"],
        }
    )


def handle_project_candidates(args: argparse.Namespace) -> None:
    try:
        evidence_root = Path(args.evidence_root).expanduser().absolute()
        homepage_article = project_scale_source_pool_homepage_article(
            evidence_root=evidence_root,
            homepage_catalog_ref=args.homepage_catalog_ref,
            homepage_catalog_digest=args.homepage_catalog_digest,
            homepage_catalog_file_sha256=args.homepage_catalog_file_sha256,
            article_catalog_ref=args.article_catalog_ref,
            article_catalog_digest=args.article_catalog_digest,
            article_catalog_file_sha256=args.article_catalog_file_sha256,
            source_ready_set_ref=args.source_ready_set_ref,
            source_ready_set_digest=args.source_ready_set_digest,
            source_ready_set_file_sha256=args.source_ready_set_file_sha256,
        )
        image_video = project_scale_source_pool_image_video(
            evidence_root=evidence_root,
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            image_catalog_refs=args.image_catalog_ref,
            image_acquisition_refs=args.image_acquisition_ref,
            image_review_refs=args.image_review_ref,
            video_catalog_refs=args.video_catalog_ref,
            video_acquisition_refs=args.video_acquisition_ref,
            video_review_refs=args.video_review_ref,
        )
        candidates = build_scale_source_pool_candidates(
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            homepage_article_projection=homepage_article,
            image_video_projection=image_video,
        )
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        destination = _canonical_candidates_destination(
            candidates,
            output_root=output_root,
        )
        frozen = write_create_once_scale_source_pool_candidates(
            destination,
            candidates,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool project-candidates] GATE_BLOCK {_typed_error(exc)}"
        ) from exc
    _print(
        {
            "schema": "quwoquan_data.scale_source_pool_candidates_write_result",
            "targetScale": frozen["targetScale"],
            "candidatesRef": destination.relative_to(output_root).as_posix(),
            "candidatesDigest": frozen["candidatesDigest"],
            "candidateCounts": frozen["candidateCounts"],
            "projectionBindings": frozen["projectionBindings"],
        }
    )


def handle_freeze_homepage_article_catalogs(args: argparse.Namespace) -> None:
    try:
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        result = freeze_homepage_article_source_ready_batch(
            Path(args.source_ready_manifest),
            evidence_root=Path(args.evidence_root),
            output_root=output_root,
            minimum_homepage_candidate_count=args.minimum_homepage_candidate_count,
            minimum_article_candidate_count=args.minimum_article_candidate_count,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool freeze-homepage-article-catalogs] GATE_BLOCK "
            f"{_typed_error(exc)}"
        ) from exc
    _print(result)


def handle_freeze_professional_image_catalog(args: argparse.Namespace) -> None:
    try:
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        catalog_root = (
            output_root / "professional-image-candidate-catalogs" / "governed"
        )
        catalog = build_professional_image_governed_candidate_catalog(
            discovery_plan_id=args.discovery_plan_id,
            discovery_plan_digest=args.discovery_plan_digest,
            created_at=args.created_at,
            evidence_root=Path(args.evidence_root),
            evidence_refs=args.evidence_ref,
        )
        destination = write_professional_image_governed_candidate_catalog(
            catalog,
            output_root=catalog_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool freeze-professional-image-catalog] GATE_BLOCK "
            f"{_typed_error(exc)}"
        ) from exc
    _print(
        {
            "schema": "quwoquan_data.professional_image_governed_catalog_write_result",
            "catalogRef": destination.relative_to(output_root).as_posix(),
            "catalogDigest": catalog["catalogDigest"],
            "catalogFileSha256": _file_sha256(destination),
            "candidateCount": catalog["candidateCount"],
            "providerCounts": catalog["providerCounts"],
        }
    )


def handle_freeze_professional_video_catalog(args: argparse.Namespace) -> None:
    from content.source.professional_video_popular_catalog import (
        build_professional_video_popular_candidate_catalog,
        write_create_once_professional_video_popular_candidate_catalog,
    )

    try:
        output_root = Path(
            args.output_root or (SOURCE_ACQUISITION_ROOT / "video")
        ).expanduser().resolve()
        catalog = build_professional_video_popular_candidate_catalog(
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            metadata_responses=_load_array(
                args.metadata_responses, label="supported API metadata responses"
            ),
            manual_file_manifests=_load_array(
                args.manual_file_manifests, label="manual video manifests"
            ),
            evidence_root=Path(args.evidence_root),
        )
        destination = (
            output_root
            / "professional-video-popular-catalogs"
            / f"{catalog['catalogDigest'].removeprefix('sha256:')}.json"
        )
        frozen = write_create_once_professional_video_popular_candidate_catalog(
            destination, catalog
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool freeze-professional-video-catalog] GATE_BLOCK "
            f"{_typed_error(exc)}"
        ) from exc
    _print({
        "schema": "quwoquan_data.professional_video_popular_catalog_write_result",
        "catalogRef": destination.relative_to(output_root).as_posix(),
        "catalogDigest": frozen["catalogDigest"],
        "catalogFileSha256": _file_sha256(destination),
        "candidateCount": frozen["candidateCount"],
        "providerCounts": frozen["providerCounts"],
    })


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "source-pool",
        help="离线冻结、验证并 create-once 写入四载体规模 source-ready pool",
    )
    commands = parser.add_subparsers(dest="source_pool_command", required=True)

    freeze_content = commands.add_parser(
        "freeze-homepage-article-catalogs",
        help="从 immutable physical capsules 单轨冻结 homepage/article catalogs",
    )
    freeze_content.add_argument("--source-ready-manifest", required=True)
    freeze_content.add_argument("--evidence-root", required=True)
    freeze_content.add_argument(
        "--minimum-homepage-candidate-count", type=int, required=True
    )
    freeze_content.add_argument(
        "--minimum-article-candidate-count", type=int, required=True
    )
    freeze_content.add_argument("--output-root")
    freeze_content.set_defaults(handler=handle_freeze_homepage_article_catalogs)

    freeze_image = commands.add_parser(
        "freeze-professional-image-catalog",
        help="从 manual_file/supported_api 证据 create-once 冻结专业图片 catalog",
    )
    freeze_image.add_argument("--discovery-plan-id", required=True)
    freeze_image.add_argument("--discovery-plan-digest", required=True)
    freeze_image.add_argument("--created-at", required=True)
    freeze_image.add_argument("--evidence-root", required=True)
    freeze_image.add_argument("--evidence-ref", action="append", required=True)
    freeze_image.add_argument("--output-root")
    freeze_image.set_defaults(handler=handle_freeze_professional_image_catalog)

    freeze_video = commands.add_parser(
        "freeze-professional-video-catalog",
        help="从 supported API metadata 与人工文件清单冻结热门视频 catalog",
    )
    freeze_video.add_argument("--source-revision", required=True)
    freeze_video.add_argument("--source-digest", required=True)
    freeze_video.add_argument("--entity-catalog-digest", required=True)
    freeze_video.add_argument("--metadata-responses", required=True)
    freeze_video.add_argument("--manual-file-manifests", required=True)
    freeze_video.add_argument("--evidence-root", required=True)
    freeze_video.add_argument("--output-root")
    freeze_video.set_defaults(handler=handle_freeze_professional_video_catalog)

    project = commands.add_parser(
        "project-candidates",
        help="从四载体 catalog/evidence 确定性 create-once 投影候选文件",
    )
    project.add_argument("--target-scale", choices=("M100", "M1000", "M10000"), required=True)
    project.add_argument("--source-revision", required=True)
    project.add_argument("--source-digest", required=True)
    project.add_argument("--entity-catalog-digest", required=True)
    project.add_argument("--evidence-root", required=True)
    project.add_argument("--output-root")
    project.add_argument("--homepage-catalog-ref", required=True)
    project.add_argument("--homepage-catalog-digest", required=True)
    project.add_argument("--homepage-catalog-file-sha256", required=True)
    project.add_argument("--article-catalog-ref", required=True)
    project.add_argument("--article-catalog-digest", required=True)
    project.add_argument("--article-catalog-file-sha256", required=True)
    project.add_argument("--source-ready-set-ref", required=True)
    project.add_argument("--source-ready-set-digest", required=True)
    project.add_argument("--source-ready-set-file-sha256", required=True)
    project.add_argument("--image-catalog-ref", action="append", required=True)
    project.add_argument("--image-acquisition-ref", action="append", required=True)
    project.add_argument("--image-review-ref", action="append", required=True)
    project.add_argument("--video-catalog-ref", action="append", required=True)
    project.add_argument("--video-acquisition-ref", action="append", required=True)
    project.add_argument("--video-review-ref", action="append", required=True)
    project.set_defaults(handler=handle_project_candidates)

    plan = commands.add_parser("plan", help="从已审核候选构建 digest-bound pool")
    plan.add_argument("--pool-id", required=True)
    plan.add_argument("--target-scale", choices=("M100", "M1000", "M10000"), required=True)
    plan.add_argument("--source-revision", required=True)
    plan.add_argument("--source-digest", required=True)
    plan.add_argument("--entity-catalog-digest", required=True)
    plan.add_argument("--created-at", required=True)
    plan.add_argument("--candidates", required=True)
    plan.set_defaults(handler=handle_plan)

    validate = commands.add_parser("validate", help="严格验证 immutable pool")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--evidence-root", required=True)
    validate.set_defaults(handler=handle_validate)

    write = commands.add_parser("write", help="按 planDigest create-once 写入 canonical workspace")
    write.add_argument("--plan", required=True)
    write.add_argument("--output-root")
    write.add_argument("--evidence-root", required=True)
    write.set_defaults(handler=handle_write)


__all__ = [
    "handle_freeze_homepage_article_catalogs",
    "handle_freeze_professional_image_catalog",
    "handle_freeze_professional_video_catalog",
    "handle_plan",
    "handle_project_candidates",
    "handle_validate",
    "handle_write",
    "register_parser",
]

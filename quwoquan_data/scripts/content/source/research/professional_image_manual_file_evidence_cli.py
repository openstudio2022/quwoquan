"""CLI binding for governed professional-image manual-file evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from core.paths import SOURCE_ACQUISITION_ROOT

from content.source.professional_image_manual_file_evidence import (
    prepare_professional_image_manual_evidence,
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _typed_message(error: Exception) -> str:
    code = str(getattr(error, "code", "") or "").strip()
    issue = str(getattr(error, "issue", "") or error).strip()
    return f"{code}: {issue}" if code else issue


def handle_prepare_professional_image_manual_evidence(
    args: argparse.Namespace,
) -> None:
    try:
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        evidence, destination = prepare_professional_image_manual_evidence(
            source_root=Path(args.source_root).expanduser().resolve(),
            source_ref=args.source_ref,
            source_sha256=args.source_sha256,
            source_attribution_root=Path(
                args.source_attribution_root
            ).expanduser().resolve(),
            source_attribution_ref=args.source_attribution_ref,
            source_attribution_sha256=args.source_attribution_sha256,
            handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
            output_root=output_root,
            provider=args.provider,
            discovery_candidate_id=args.discovery_candidate_id,
            source_page_url=args.source_page_url,
            creator=args.creator,
            title=args.title,
            observed_at=args.observed_at,
            rights_status=args.rights_status,
            license_name=args.license,
            license_snapshot=args.license_snapshot,
            usage_scope=args.usage_scope,
            model_release_status=args.model_release_status,
            terms_url=args.terms_url,
            authorization_proof=args.authorization_proof,
            rights_issues=args.rights_issue or (),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool prepare-professional-image-manual-evidence] "
            f"GATE_BLOCK {_typed_message(exc)}"
        ) from exc
    print(
        json.dumps(
            {
                "schema": (
                    "quwoquan_data.professional_image_manual_evidence_write_result"
                ),
                "evidenceRef": destination.relative_to(output_root).as_posix(),
                "evidenceDigest": evidence["evidenceDigest"],
                "evidenceFileSha256": _file_sha256(destination),
                "manualFile": evidence["manualFile"],
                "sourceAttributionFile": evidence["sourceAttributionFile"],
                "contentSha256": evidence["contentSha256"],
                "sourceRevision": evidence["sourceRevision"],
                "sourceDigest": evidence["sourceDigest"],
                "entityCatalogDigest": evidence["entityCatalogDigest"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def register_professional_image_manual_file_evidence_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "prepare-professional-image-manual-evidence",
        help="从显式原始图片、current handoff 与 attribution/rights 事实生成 create-once 证据",
    )
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--source-attribution-root", required=True)
    parser.add_argument("--source-attribution-ref", required=True)
    parser.add_argument("--source-attribution-sha256", required=True)
    parser.add_argument("--handoff-ref", required=True)
    parser.add_argument("--output-root")
    parser.add_argument(
        "--provider",
        choices=("pinterest", "tuchong", "wikimedia_commons", "openverse"),
        required=True,
    )
    parser.add_argument("--discovery-candidate-id", required=True)
    parser.add_argument("--source-page-url", required=True)
    parser.add_argument("--creator", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument(
        "--rights-status",
        choices=("verified", "unverified", "restricted", "unknown"),
        required=True,
    )
    parser.add_argument("--license", required=True)
    parser.add_argument("--license-snapshot", required=True)
    parser.add_argument(
        "--usage-scope",
        choices=("internal_reference", "app_publish", "editorial"),
        required=True,
    )
    parser.add_argument(
        "--model-release-status",
        choices=("not_required", "obtained", "editorial_only"),
        required=True,
    )
    parser.add_argument("--terms-url", required=True)
    parser.add_argument("--authorization-proof", required=True)
    parser.add_argument("--rights-issue", action="append")
    parser.set_defaults(handler=handle_prepare_professional_image_manual_evidence)


__all__ = [
    "handle_prepare_professional_image_manual_evidence",
    "register_professional_image_manual_file_evidence_parser",
]

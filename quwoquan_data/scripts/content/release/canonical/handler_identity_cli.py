"""Argparse bindings for immutable release identity evidence commands."""

from __future__ import annotations

import argparse


def register_identity_parsers(
    commands: argparse._SubParsersAction,
    *,
    owner: object,
) -> None:
    identity_incident = commands.add_parser(
        "identity-incident",
        help="记录同一 releaseId 的冲突 immutable identity；不修改任何 release",
    )
    identity_incident.add_argument("--release-id", required=True)
    identity_incident.add_argument("--incident-id", required=True)
    identity_incident.add_argument(
        "--original-attestation",
        action="append",
        default=[],
        help="原始留存的 release attestation 文件；可重复",
    )
    identity_incident.add_argument(
        "--recovery-provenance",
        action="append",
        default=[],
        help="deterministic_byte_reconstruction 的 create-once provenance；可重复",
    )
    identity_incident.add_argument("--output-root")
    identity_incident.set_defaults(handler=owner.handle_release_identity_incident)

    identity_recovery = commands.add_parser(
        "identity-recovery",
        help="按冻结 JSON 序列化合同写确定性 attestation 恢复物与 provenance",
    )
    identity_recovery.add_argument("--release-id", required=True)
    identity_recovery.add_argument("--recovery-id", required=True)
    identity_recovery.add_argument("--attestation-document", required=True)
    identity_recovery.add_argument("--template-attestation", required=True)
    identity_recovery.add_argument("--target-attestation-sha256", required=True)
    identity_recovery.add_argument("--writer-revision", required=True)
    identity_recovery.add_argument(
        "--writer-source",
        action="append",
        required=True,
        help="历史 writer 闭集，格式 <logicalRef>=<snapshotPath>；必须四项",
    )
    identity_recovery.add_argument("--recovered-recorded-at", required=True)
    identity_recovery.add_argument("--search-start-at", required=True)
    identity_recovery.add_argument("--search-end-at", required=True)
    identity_recovery.add_argument(
        "--evidence",
        action="append",
        required=True,
        help=(
            "独立证据，格式 <role>=<path>；必须各提供 "
            "release_identity 与 execution_closure"
        ),
    )
    identity_recovery.add_argument("--output-root")
    identity_recovery.set_defaults(handler=owner.handle_release_identity_recovery)


__all__ = ["register_identity_parsers"]

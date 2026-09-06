"""最终验收的常量、数据类、类型别名与 blocker 聚合器（自原单文件逐字搬移）。"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

SCHEMA = "qwq.environment_stability_final_acceptance"
# 原文件位于 lib/ 下用 parents[2]；本模块深一层，用 parents[3] 指向 quwoquan_ops。
SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "gate"
    / "environment_stability_final_acceptance.schema.json"
)
BLOCKED_VERDICT = "GATE_BLOCK"
MAX_FUTURE_SKEW_SECONDS = 300
ENVIRONMENTS = ("alpha", "beta", "gamma")
PROVIDER_NONPROD_ENVIRONMENTS = ("alpha", "beta", "gamma")
REQUIRED_SOAK_CLAIMS = frozenset(
    {"soak", "fresh", "credentials", "approval"}
)
RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS = frozenset(
    {"recovery.ios", "recovery.android", "nightly"}
)
GITHUB_ATTESTED_WORKFLOW_BY_KIND = {
    "prod_sim": ".github/workflows/prod-sim-manual-admission.yml",
}

_GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_RECEIPT_ID = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_INPUT_NAMES = frozenset({"verdict.json", "todo.json", "todos.json"})
_SELF_AUTHORITY_FIELDS = frozenset(
    {
        "sourceauthority",
        "authorityverification",
        "credentialreceiptreff",
        "credentialreceiptrefs",
        "approvalreceiptref",
        "realreceipt",
    }
)

BLOCKER_CODES = frozenset(
    {
        "MISSING_INPUT",
        "UNREADABLE_INPUT",
        "UNSUPPORTED_INPUT",
        "SCHEMA_MISMATCH",
        "STATUS_NOT_PASSED",
        "STALE_EVIDENCE",
        "IDENTITY_MISMATCH",
        "DIGEST_MISMATCH",
        "NON_PROMOTABLE",
        "LOCAL_ATTESTATION",
        "EXPECTED_SKIP",
        "ARTIFACT_CLOSURE_INVALID",
        "UNVERIFIABLE_AUTHORITY",
        "HOSTED_READBACK_INVALID",
    }
)


@dataclass(frozen=True)
class FinalAcceptanceInputs:
    artifact_root: Path | None = None
    candidate_manifest: Path | None = None
    pilot_release_attestation: Path | None = None
    pilot_rollback_attestation: Path | None = None
    content_lifecycle_alpha: Path | None = None
    content_lifecycle_beta: Path | None = None
    content_lifecycle_gamma: Path | None = None
    local_env_green_matrix: Path | None = None
    ios_recovery_uat: Path | None = None
    android_recovery_uat: Path | None = None
    nightly_artifact: Path | None = None
    prod_sim_receipt: Path | None = None
    prod_rollout_readback: Path | None = None
    prod_rollback_readback: Path | None = None
    prod_soak_readback: Path | None = None

    def receipt_paths(self) -> dict[str, Path | None]:
        return {
            "candidate": self.candidate_manifest,
            "pilot.release": self.pilot_release_attestation,
            "pilot.rollback": self.pilot_rollback_attestation,
            "content.alpha": self.content_lifecycle_alpha,
            "content.beta": self.content_lifecycle_beta,
            "content.gamma": self.content_lifecycle_gamma,
            "local_env.green_matrix": self.local_env_green_matrix,
            "recovery.ios": self.ios_recovery_uat,
            "recovery.android": self.android_recovery_uat,
            "nightly": self.nightly_artifact,
            "prod_sim": self.prod_sim_receipt,
            "prod.rollout_readback": self.prod_rollout_readback,
            "prod.rollback_readback": self.prod_rollback_readback,
            "prod.soak_readback": self.prod_soak_readback,
        }


@dataclass(frozen=True)
class LoadedReceipt:
    label: str
    path: Path
    payload: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class VerifiedAuthority:
    """Result returned only by a trusted external verifier."""

    authority: str
    subject_digest: str
    verification_digest: str
    claims: frozenset[str] = frozenset()


AttestationVerifier = Callable[
    [Path, str, Mapping[str, Any]],
    VerifiedAuthority,
]
ProviderReadinessVerifier = Callable[
    [Path, Mapping[str, Any], list[Mapping[str, Any]], Mapping[str, Any]],
    VerifiedAuthority,
]
SoakAuthorityVerifier = Callable[
    [Path, Mapping[str, Any], Mapping[str, Any]],
    VerifiedAuthority,
]


class ArtifactClosureVerifier(Protocol):
    def __call__(
        self,
        manifest: dict[str, Any],
        *,
        artifact_dir: Path | None = None,
        allowed_statuses: Iterable[str] | None = None,
    ) -> dict[str, Any]: ...


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class _Evaluation:
    def __init__(self) -> None:
        self.blockers: list[dict[str, str]] = []
        self.observed_at: dict[str, str] = {}
        self.authority: dict[str, VerifiedAuthority] = {}

    def block(self, code: str, label: str, message: str) -> None:
        if code not in BLOCKER_CODES:
            raise ValueError(f"unknown final-acceptance blocker code: {code}")
        blocker = {"code": code, "input": label, "message": message}
        if blocker not in self.blockers:
            self.blockers.append(blocker)

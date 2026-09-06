#!/usr/bin/env python3
"""Exact integration candidate 的 canonical CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.integration_qualification import (  # noqa: E402
    IntegrationQualificationError,
    hmac_sha256_environment_verifier,
    hmac_sha256_signer,
    issue_integration_qualification,
)
from quwoquan_ops.ci.scoped_candidate import (  # noqa: E402
    ScopedCandidateError,
    acquire_claim,
    build_candidate,
    create_publish_admission,
    exact_digest,
    hosted_broker_cas_publish,
    inspect_claims,
    release_claim,
)

POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build exact scoped integration candidates"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    claim = sub.add_parser("claim")
    claim.add_argument("--writer", required=True)
    claim.add_argument("--owner-identity", required=True)
    claim.add_argument("--expected-parent", required=True)
    claim.add_argument("--expires-at", required=True)
    claim.add_argument("paths", nargs="+")
    build = sub.add_parser("build")
    build.add_argument("--claim-ref", required=True)
    build.add_argument("--owner-identity", required=True)
    build.add_argument("--impact-plan-digest", required=True)
    build.add_argument("--message", required=True)
    build.add_argument("--author-name", required=True)
    build.add_argument("--author-email", required=True)
    admit = sub.add_parser("admit")
    admit.add_argument("--candidate-ref", required=True)
    admit.add_argument("--candidate-digest", required=True)
    admit.add_argument("--source-fact", action="append", required=True)
    admit.add_argument("--alpha-fact-ref", required=True)
    admit.add_argument("--alpha-fact-digest", required=True)
    admit.add_argument("--beta-fact-ref", required=True)
    admit.add_argument("--beta-fact-digest", required=True)
    admit.add_argument("--expected-remote-oid", required=True)
    qualify = sub.add_parser("qualify")
    qualify.add_argument("--publish-result-ref", required=True)
    qualify.add_argument("--publish-result-digest", required=True)
    qualify.add_argument("--gamma-fact-ref", required=True)
    qualify.add_argument("--gamma-fact-digest", required=True)
    qualify.add_argument("--qualification-signer-identity", required=True)
    qualify.add_argument("--qualification-signing-key-env", required=True)
    qualify.add_argument("--environment-verification-key-env", required=True)
    for environment in ("alpha", "beta", "gamma"):
        qualify.add_argument(f"--expected-{environment}-signer-identity", required=True)
    qualify.add_argument("--issued-at", required=True)
    qualify.add_argument("--expires-at", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--admission-ref", required=True)
    publish.add_argument("--broker-url", required=True)
    publish.add_argument("--token-env", default="QWQ_INTEGRATION_PUBLISHER_TOKEN")
    release = sub.add_parser("release")
    release.add_argument("--claim-ref", required=True)
    release.add_argument("--reason", required=True)
    sub.add_parser("inspect")
    args = parser.parse_args(argv)
    try:
        if args.command == "claim":
            path = acquire_claim(
                repository=ROOT,
                policy_path=POLICY,
                writer_id=args.writer,
                owner_identity_ref=args.owner_identity,
                expected_parent=args.expected_parent,
                paths=args.paths,
                expires_at=args.expires_at,
            )
            result: object = {
                "ref": str(path.relative_to(ROOT)),
                "digest": exact_digest(path),
            }
        elif args.command == "build":
            path = build_candidate(
                repository=ROOT,
                policy_path=POLICY,
                claim_ref=ROOT / args.claim_ref,
                owner_identity_ref=args.owner_identity,
                impact_plan_digest=args.impact_plan_digest,
                message=args.message,
                author_name=args.author_name,
                author_email=args.author_email,
            )
            result = {"ref": str(path.relative_to(ROOT)), "digest": exact_digest(path)}
        elif args.command == "admit":
            source_facts = []
            for value in args.source_fact:
                try:
                    ref, digest = value.split("=", 1)
                except ValueError as error:
                    raise ScopedCandidateError(
                        "SCOPED_CANDIDATE.INVALID", "--source-fact must be ref=digest"
                    ) from error
                source_facts.append({"ref": ref, "digest": digest})
            path = create_publish_admission(
                repository=ROOT,
                policy_path=POLICY,
                candidate_ref={
                    "ref": args.candidate_ref,
                    "digest": args.candidate_digest,
                },
                source_fact_refs=source_facts,
                alpha_fact_ref={
                    "ref": args.alpha_fact_ref,
                    "digest": args.alpha_fact_digest,
                },
                beta_fact_ref={
                    "ref": args.beta_fact_ref,
                    "digest": args.beta_fact_digest,
                },
                expected_remote_oid=args.expected_remote_oid,
            )
            result = {"ref": str(path.relative_to(ROOT)), "digest": exact_digest(path)}
        elif args.command == "qualify":
            import hmac
            import os

            if (
                args.qualification_signing_key_env
                == args.environment_verification_key_env
            ):
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.KEY_PURPOSE_CONFLICT",
                    "qualification signing and environment verification key sources must differ",
                )
            qualification_key = os.environ.get(
                args.qualification_signing_key_env, ""
            ).encode("utf-8")
            if not qualification_key:
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.QUALIFICATION_SIGNER_UNAVAILABLE",
                    "integration qualification signing key is missing",
                )
            environment_key = os.environ.get(
                args.environment_verification_key_env, ""
            ).encode("utf-8")
            if not environment_key:
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.ENVIRONMENT_VERIFIER_UNAVAILABLE",
                    "environment acceptance verification key is missing",
                )
            if hmac.compare_digest(qualification_key, environment_key):
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.KEY_PURPOSE_CONFLICT",
                    "qualification signing and environment verification keys must differ",
                )
            expected_environment_signers = {
                environment: getattr(args, f"expected_{environment}_signer_identity")
                for environment in ("alpha", "beta", "gamma")
            }
            path = issue_integration_qualification(
                repository=ROOT,
                store_root=ROOT / ".qwq_output/env/repo/local/scoped-candidate/process",
                publish_result_ref={
                    "ref": args.publish_result_ref,
                    "digest": args.publish_result_digest,
                },
                gamma_acceptance_ref={
                    "ref": args.gamma_fact_ref,
                    "digest": args.gamma_fact_digest,
                },
                signer_identity=args.qualification_signer_identity,
                signer=hmac_sha256_signer(qualification_key),
                environment_signature_verifier=hmac_sha256_environment_verifier(
                    {
                        identity: environment_key
                        for identity in expected_environment_signers.values()
                    }
                ),
                expected_environment_signer_identities=(expected_environment_signers),
                issued_at=args.issued_at,
                expires_at=args.expires_at,
            )
            result = {"ref": str(path.relative_to(ROOT)), "digest": exact_digest(path)}
        elif args.command == "publish":
            import os

            path = hosted_broker_cas_publish(
                repository=ROOT,
                policy_path=POLICY,
                admission_ref=ROOT / args.admission_ref,
                broker_url=args.broker_url,
                token_provider=lambda: os.environ.get(args.token_env, ""),
            )
            result = {"ref": str(path.relative_to(ROOT)), "digest": exact_digest(path)}
        elif args.command == "release":
            path = release_claim(
                repository=ROOT,
                policy_path=POLICY,
                claim_ref=ROOT / args.claim_ref,
                reason=args.reason,
            )
            result = {"ref": str(path.relative_to(ROOT)), "digest": exact_digest(path)}
        else:
            result = inspect_claims(repository=ROOT, policy_path=POLICY)
    except (ScopedCandidateError, IntegrationQualificationError) as exc:
        print(
            json.dumps(
                {"terminal": "GATE_BLOCK", "code": exc.code, "detail": exc.detail},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

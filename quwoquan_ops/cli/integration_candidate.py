#!/usr/bin/env python3
"""Exact integration candidate 的 canonical CLI。

链内所有 ref 都相对唯一 store root（`scoped_candidate_policy.yaml#claim.storage_root`）
解析，与 `environment_execution.py --store-root` 使用同一根；输出的 `ref` 同样是
store-relative，可直接回传给后续子命令。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.integration_qualification import (
    IntegrationQualificationError,
    issue_integration_qualification,
)
from quwoquan_ops.ci.scoped_candidate import (
    ScopedCandidateError,
    acquire_claim,
    build_candidate,
    build_head_candidate,
    create_publish_admission,
    create_source_fact,
    hosted_broker_cas_publish,
    inspect_claims,
    local_git_cas_publish,
    release_claim,
    store_ref,
    store_root,
)
from quwoquan_ops.cli.lib.evidence_signing import (
    DEFAULT_KEYRING_PATH,
    EvidenceSigningError,
    assert_distinct_active_keys,
    ed25519_environment_verifier,
    ed25519_signer,
    key_root,
    load_keyring,
)

POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"


def _exact(value: str, flag: str) -> dict[str, str]:
    try:
        ref, digest = value.rsplit("=", 1)
    except ValueError as error:
        raise ScopedCandidateError(
            "SCOPED_CANDIDATE.INVALID", f"{flag} must be <store-relative ref>=<sha256:digest>"
        ) from error
    return {"ref": ref, "digest": digest}


def _store_ref(path: Path) -> dict[str, str]:
    return store_ref(repository=ROOT, policy_path=POLICY, path=path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    claim = sub.add_parser("claim", help="为不重叠整文件 scope 取得 append-only claim")
    claim.add_argument("--writer", required=True)
    claim.add_argument("--owner-identity", required=True)
    claim.add_argument("--expected-parent", required=True)
    claim.add_argument("--expires-at", required=True)
    claim.add_argument("paths", nargs="+")

    build = sub.add_parser("build", help="以私有 index 从 claim 构造 exact candidate commit")
    build.add_argument("--claim-ref", required=True, help="store-relative claim ref")
    build.add_argument("--owner-identity", required=True)
    build.add_argument("--impact-plan-digest", required=True)
    build.add_argument("--message", required=True)
    build.add_argument("--author-name", required=True)
    build.add_argument("--author-email", required=True)

    head = sub.add_parser("build-head", help="把已存在的 exact commit（HEAD 或 lane head）构造为 candidate")
    head.add_argument("--commit", default="HEAD")
    head.add_argument("--expected-parent", required=True, help="必须是远端 dev1.0 当前 OID")
    head.add_argument("--owner-identity", required=True)
    head.add_argument("--impact-plan-digest", required=True)
    head.add_argument("--writer", required=True)
    head.add_argument("--expires-at", required=True)

    source = sub.add_parser("source-fact", help="把本地 readiness/gate 回执绑定到 candidate")
    source.add_argument("--candidate", required=True, help="<store-relative ref>=<digest>")
    source.add_argument("--kind", required=True, choices=("local_readiness_fast", "local_readiness_scope", "commit_gate"))
    source.add_argument("--receipt", required=True, type=Path, help="仓内 .qwq_output 下的回执文件")
    source.add_argument("--status", required=True, choices=("passed", "failed"))

    admit = sub.add_parser("admit", help="以 source facts + Alpha/Beta EAF 形成 publish admission")
    admit.add_argument("--candidate", required=True, help="<store-relative ref>=<digest>")
    admit.add_argument("--source-fact", action="append", required=True, help="<store-relative ref>=<digest>")
    admit.add_argument("--alpha-fact", required=True, help="<store-relative ref>=<digest>")
    admit.add_argument("--beta-fact", required=True, help="<store-relative ref>=<digest>")
    admit.add_argument("--expected-remote-oid", required=True)

    publish = sub.add_parser("publish", help="按 admission 发布到 dev1.0 并读回终态")
    publish.add_argument("--admission-ref", required=True, help="store-relative admission ref")
    publish.add_argument("--adapter", choices=("local-git", "hosted-broker"), default="local-git")
    publish.add_argument("--remote", default="origin")
    publish.add_argument("--broker-url")
    publish.add_argument("--token-env", default="QWQ_INTEGRATION_PUBLISHER_TOKEN")

    qualify = sub.add_parser("qualify", help="以 publish result + Gamma EAF 签发 IntegrationQualificationFact")
    qualify.add_argument("--publish-result", required=True, help="<store-relative ref>=<digest>")
    qualify.add_argument("--gamma-fact", required=True, help="<store-relative ref>=<digest>")
    qualify.add_argument("--qualification-signer-identity", required=True)
    qualify.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH,
                         help="仓内 Ed25519 公钥 keyring；qualification 私钥来自仓外 QWQ_EVIDENCE_SIGNING_KEY_ROOT")
    for environment in ("alpha", "beta", "gamma"):
        qualify.add_argument(f"--expected-{environment}-signer-identity", required=True)
    qualify.add_argument("--issued-at", required=True)
    qualify.add_argument("--expires-at", required=True)

    release = sub.add_parser("release", help="显式释放 claim")
    release.add_argument("--claim-ref", required=True, help="store-relative claim ref")
    release.add_argument("--reason", required=True)

    sub.add_parser("inspect", help="列出 claim 与其 active 状态")
    sub.add_parser("store-root", help="打印链内 ref 的唯一 store root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        root = store_root(repository=ROOT, policy_path=POLICY)
        if args.command == "claim":
            path = acquire_claim(
                repository=ROOT, policy_path=POLICY, writer_id=args.writer,
                owner_identity_ref=args.owner_identity, expected_parent=args.expected_parent,
                paths=args.paths, expires_at=args.expires_at,
            )
            result: object = _store_ref(path)
        elif args.command == "build":
            path = build_candidate(
                repository=ROOT, policy_path=POLICY, claim_ref=root / args.claim_ref,
                owner_identity_ref=args.owner_identity, impact_plan_digest=args.impact_plan_digest,
                message=args.message, author_name=args.author_name, author_email=args.author_email,
            )
            result = _store_ref(path)
        elif args.command == "build-head":
            path = build_head_candidate(
                repository=ROOT, policy_path=POLICY, commit=args.commit,
                expected_parent=args.expected_parent, owner_identity_ref=args.owner_identity,
                impact_plan_digest=args.impact_plan_digest, writer_id=args.writer,
                expires_at=args.expires_at,
            )
            body = json.loads(path.read_text(encoding="utf-8"))
            result = {
                **_store_ref(path),
                "candidateId": body["candidateId"], "commit": body["commit"], "tree": body["tree"],
                "claimRef": body["claimRef"], "changedPaths": len(body["paths"]),
            }
        elif args.command == "source-fact":
            path = create_source_fact(
                repository=ROOT, policy_path=POLICY, candidate_ref=_exact(args.candidate, "--candidate"),
                kind=args.kind, receipt_path=args.receipt, status=args.status,
            )
            result = _store_ref(path)
        elif args.command == "admit":
            path = create_publish_admission(
                repository=ROOT, policy_path=POLICY,
                candidate_ref=_exact(args.candidate, "--candidate"),
                source_fact_refs=[_exact(value, "--source-fact") for value in args.source_fact],
                alpha_fact_ref=_exact(args.alpha_fact, "--alpha-fact"),
                beta_fact_ref=_exact(args.beta_fact, "--beta-fact"),
                expected_remote_oid=args.expected_remote_oid,
            )
            result = _store_ref(path)
        elif args.command == "publish":
            if args.adapter == "hosted-broker":
                if not args.broker_url:
                    raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "--broker-url is required for hosted-broker")
                path = hosted_broker_cas_publish(
                    repository=ROOT, policy_path=POLICY, admission_ref=root / args.admission_ref,
                    broker_url=args.broker_url, token_provider=lambda: os.environ.get(args.token_env, ""),
                )
            else:
                path = local_git_cas_publish(
                    repository=ROOT, policy_path=POLICY, admission_ref=root / args.admission_ref,
                    remote=args.remote,
                )
            body = json.loads(path.read_text(encoding="utf-8"))
            result = {**_store_ref(path), "beforeOid": body["beforeOid"], "afterOid": body["afterOid"], "readbackOid": body["readbackOid"]}
        elif args.command == "qualify":
            expected_environment_signers = {
                environment: getattr(args, f"expected_{environment}_signer_identity")
                for environment in ("alpha", "beta", "gamma")
            }
            try:
                keyring = load_keyring(args.signing_keyring)
                for identity in expected_environment_signers.values():
                    assert_distinct_active_keys(keyring, args.qualification_signer_identity, identity)
                environment_verifier = ed25519_environment_verifier(keyring, expected_environment_signers.values())
            except EvidenceSigningError as exc:
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.KEY_PURPOSE_CONFLICT"
                    if exc.code == "EVIDENCE_SIGNING.KEY_PURPOSE_CONFLICT"
                    else "SCOPED_CANDIDATE.ENVIRONMENT_VERIFIER_UNAVAILABLE",
                    exc.detail,
                ) from exc
            try:
                qualification_signer = ed25519_signer(
                    args.qualification_signer_identity, root=key_root(), keyring=keyring,
                )
            except EvidenceSigningError as exc:
                raise ScopedCandidateError("SCOPED_CANDIDATE.QUALIFICATION_SIGNER_UNAVAILABLE", exc.detail) from exc
            path = issue_integration_qualification(
                repository=ROOT, store_root=root,
                publish_result_ref=_exact(args.publish_result, "--publish-result"),
                gamma_acceptance_ref=_exact(args.gamma_fact, "--gamma-fact"),
                signer_identity=args.qualification_signer_identity,
                signer=qualification_signer,
                environment_signature_verifier=environment_verifier,
                expected_environment_signer_identities=expected_environment_signers,
                issued_at=args.issued_at, expires_at=args.expires_at,
            )
            result = _store_ref(path)
        elif args.command == "release":
            path = release_claim(
                repository=ROOT, policy_path=POLICY, claim_ref=root / args.claim_ref, reason=args.reason,
            )
            result = _store_ref(path)
        elif args.command == "store-root":
            result = {"storeRoot": root.relative_to(ROOT).as_posix()}
        else:
            result = inspect_claims(repository=ROOT, policy_path=POLICY)
    except (ScopedCandidateError, IntegrationQualificationError) as exc:
        print(
            json.dumps(
                {"terminal": "GATE_BLOCK", "code": exc.code, "detail": exc.detail},
                ensure_ascii=False, sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

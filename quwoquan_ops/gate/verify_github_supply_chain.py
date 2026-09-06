#!/usr/bin/env python3
"""阻断浮动 Action、越权权限和 GitHub 发布供应链静态合同漂移。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_ACTION_PATTERN = re.compile(r"^[^/@\s]+/[^@\s]+(?:/[^@\s]+)*@[0-9a-f]{40}$")
REQUIRED_CODEOWNER_PATHS = {
    "*",
    "/.github/workflows/",
    "/quwoquan_ops/",
    "/quwoquan_service/contracts/metadata/",
    "/specs/feature-tree/platform-ops-governance/",
}
RELEASE_WORKFLOWS = {
    "qualification": WORKFLOWS / "release-qualification.yml",
    "selection": WORKFLOWS / "release-tag-selection.yml",
    "production": WORKFLOWS / "deploy-prod-auto.yml",
}
ATTEST_ACTION = "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6"


def _read_workflow(name: str) -> tuple[Path, str] | None:
    path = RELEASE_WORKFLOWS[name]
    if not path.is_file():
        return None
    return path, path.read_text(encoding="utf-8")


def _require_tokens(
    path: Path, text: str, tokens: tuple[str, ...], control: str,
) -> list[str]:
    return [
        f"{path.relative_to(ROOT)} missing {control}: {token}"
        for token in tokens
        if token not in text
    ]


def _forbid_tokens(
    path: Path, text: str, tokens: tuple[str, ...], control: str,
) -> list[str]:
    return [
        f"{path.relative_to(ROOT)} contains forbidden {control}: {token}"
        for token in tokens
        if token in text
    ]


def _top_level_permissions(text: str) -> set[str]:
    lines = text.splitlines()
    try:
        start = lines.index("permissions:")
    except ValueError:
        return set()
    permissions: set[str] = set()
    for line in lines[start + 1 :]:
        if line and not line.startswith((" ", "\t")):
            break
        entry = line.strip()
        if entry and not entry.startswith("#"):
            permissions.add(entry)
    return permissions


def _dispatch_inputs(text: str) -> set[str]:
    match = re.search(
        r"(?ms)^  workflow_dispatch:\s*\n(?:^    [^\n]*\n)*?^    inputs:\s*\n(?P<body>.*?)(?=^  \S|^\S|\Z)",
        text,
    )
    if match is None:
        return set()
    return set(re.findall(r"(?m)^      ([a-z][a-z0-9_]*):\s*$", match.group("body")))


def _verify_dispatch_inputs(
    path: Path, text: str, expected: set[str],
) -> list[str]:
    actual = _dispatch_inputs(text)
    if actual == expected:
        return []
    return [
        f"{path.relative_to(ROOT)} workflow_dispatch inputs must be "
        f"{sorted(expected)}; got {sorted(actual)}"
    ]


def _verify_top_level_permissions(
    path: Path, text: str, expected: set[str],
) -> list[str]:
    actual = _top_level_permissions(text)
    if actual == expected:
        return []
    return [
        f"{path.relative_to(ROOT)} top-level permissions must be "
        f"{sorted(expected)}; got {sorted(actual)}"
    ]


def _executable_token_index(text: str, token: str, start: int = 0) -> int:
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if offset >= start and stripped and not stripped.startswith("#") and token in line:
            return offset + line.index(token)
        offset += len(line)
    return -1


def verify_action_pins() -> list[str]:
    failures: list[str] = []
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        permissions = _top_level_permissions(text)
        if "contents: read" not in permissions:
            failures.append(
                f"{path.relative_to(ROOT)}: top-level permissions must include contents: read"
            )
        if any(item == "write-all" for item in permissions):
            failures.append(
                f"{path.relative_to(ROOT)}: top-level write-all permission is forbidden"
            )
        for match in USES_PATTERN.finditer(text):
            reference = match.group(1)
            if reference.startswith("./") or reference.startswith("docker://"):
                continue
            if PINNED_ACTION_PATTERN.fullmatch(reference) is None:
                line = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{path.relative_to(ROOT)}:{line}: third-party action must use a full "
                    f"40-character commit SHA: {reference}"
                )
    return failures


def verify_release_qualification_controls() -> list[str]:
    current = _read_workflow("qualification")
    if current is None:
        return [".github/workflows/release-qualification.yml is required"]
    path, text = current
    failures = _verify_top_level_permissions(path, text, {"contents: read"})
    failures += _verify_dispatch_inputs(
        path,
        text,
        {
            "rc_tag_admission_ref",
            "qualification_request_ref",
            "source_git_sha",
            "product_version_manifest_ref",
            "package_acceptance_fact_ref",
            "provider_fact_ref",
            "uat_fact_ref",
            "supply_chain_fact_ref",
        },
    )
    failures += _require_tokens(
        path,
        text,
        (
            "environment: release-qualification",
            "allocate_build_number:",
            "artifact_build_number.py",
            "uses: ./.github/workflows/service_pipeline.yml",
            "uses: ./.github/workflows/app_pipeline.yml",
            "qualification_request_ref:",
            "qualification_request_digest:",
            "rc_tag_admission_ref:",
            "ref: ${{ inputs.source_git_sha }}",
            "persist-credentials: false",
            "CandidateMaterialManifest",
        ),
        "RC build-once qualification control",
    )
    failures += _forbid_tokens(
        path,
        text,
        (
            "pull-requests: read",
            "contents: write",
            "runs-on: [self-hosted",
            "environment: production",
            "verify_release_governance.py",
            "governance-receipt.json",
            "git tag -a",
            "stackctl.py deploy",
        ),
        "RC qualification authority",
    )
    material = _executable_token_index(text, "qualification-material")
    finalized = _executable_token_index(text, "qualification-finalize")
    if min(material, finalized) < 0 or material > finalized or any(
        token in text
        for token in (
            "CandidateMaterialManifest creation is authorized only",
            "They must publish one CandidateMaterialManifest",
        )
    ):
        failures.append(
            f"{path.relative_to(ROOT)} is still a qualification placeholder: "
            "the exact reusable factory outputs must create CandidateMaterialManifest bytes"
        )
    return failures


def verify_release_tag_selection_controls() -> list[str]:
    current = _read_workflow("selection")
    if current is None:
        return [".github/workflows/release-tag-selection.yml is required"]
    path, text = current
    failures = _verify_top_level_permissions(path, text, {"contents: read"})
    failures += _verify_dispatch_inputs(
        path,
        text,
        {
            "tag_kind",
            "tag_name",
            "source_git_sha",
            "selection_fact_ref",
            "initial_release_authority_ref",
            "selected_rc_admission_ref",
            "qualification_fact_ref",
            "release_authority_fact_ref",
        },
    )
    failures += _require_tokens(
        path,
        text,
        (
            "group: release-tag-controller",
            "cancel-in-progress: false",
            "environment: release-selection",
            # controller 即 hosted deploy key（DEC-009）：私钥只在 mutation step 短时物化，
            # 指纹与 REST /keys 读回比对，tagger 身份即 controller title。
            "CONTROLLER_TITLE: release-controller",
            "RELEASE_CONTROLLER_DEPLOY_KEY: ${{ secrets.RELEASE_CONTROLLER_DEPLOY_KEY }}",
            "ssh-keygen -lf",
            'test "$LOCAL_FINGERPRINT" = "$HOSTED_FINGERPRINT"',
            'export GIT_SSH_COMMAND="ssh -i $KEY_FILE -o IdentitiesOnly=yes',
            'git remote set-url origin "ssh://git@${GITHUB_SERVER_URL#https://}/${GITHUB_REPOSITORY}.git"',
            'git remote set-url origin "https://github.com/${GITHUB_REPOSITORY}.git"',
            'rm -f "$KEY_FILE"',
            "persist-credentials: false",
            "quwoquan_ops/ci/release_tag_readback.py",
            "--phase pre_mutation",
            "--phase post_mutation",
            "tag-admit-rc-intent",
            "tag-admit-stable-intent",
            "tag-admission-intent-check",
            "git merge-base --is-ancestor",
            "! git ls-remote --exit-code --tags origin",
            "already exists before mutation",
            'git tag -a "$TAG" "$SOURCE_SHA"',
            "release-tag-intent: $INTENT_ID",
            'test "$(git cat-file -t "refs/tags/$TAG")" = tag',
            'git push origin "refs/tags/$TAG:refs/tags/$TAG"',
            "/git/ref/tags/${TAG}",
            "/git/tags/${REMOTE_OBJECT_OID}",
            'test "$TAG_OBJECT_OID" = "$REMOTE_OBJECT_OID"',
            'test "$(git rev-parse "refs/tags/$TAG^{}")" = "$SOURCE_SHA"',
            "tag-mutation-outcome",
            '"tag-admit-$KIND-finalize"',
        ),
        "trusted two-phase release tag controller control",
    )
    failures += _forbid_tokens(
        path,
        text,
        (
            "pull-requests: read",
            "attestations: write",
            "checks: write",
            "runs-on: [self-hosted",
            "environment: production",
            "build_sign_attest_once",
            "stackctl.py deploy",
            # 旧 controller App / 外部 readback 服务已退役：唯一 controller 是 hosted deploy key。
            "actions/create-github-app-token@",
            "RELEASE_CONTROLLER_APP_ID",
            "RELEASE_CONTROLLER_APP_PRIVATE_KEY",
            "RELEASE_CONTROLLER_INSTALLATION_ID",
            "RELEASE_CONTROLLER_APP_SLUG",
            "RELEASE_CONTROLLER_READBACK_URL",
            "RELEASE_CONTROLLER_READBACK_TOKEN",
            "x-access-token:",
            "creator_readback_ref",
            "ruleset_readback_ref",
            "git fetch --force",
            "git fetch -f",
            "git tag -f",
            "git tag --force",
            "git tag -d",
            "git tag --delete",
            "git push --force",
            "git push -f",
            "git push --delete",
            'git push origin ":refs/tags/',
            "+refs/tags/",
            "git update-ref refs/tags/",
            "--request PATCH",
            "--request DELETE",
            '"force": true',
            '"creator":',
            "EXPECTED_CREATOR=",
        ),
        "release tag authority",
    )

    pre_readback = _executable_token_index(text, "--phase pre_mutation")
    admit_rc = _executable_token_index(text, "tag-admit-rc-intent")
    admit_stable = _executable_token_index(text, "tag-admit-stable-intent")
    intent_check = _executable_token_index(text, "tag-admission-intent-check")
    remote_absent = _executable_token_index(text, "already exists before mutation", intent_check + 1)
    key_match = _executable_token_index(text, 'test "$LOCAL_FINGERPRINT" = "$HOSTED_FINGERPRINT"')
    ssh_remote = _executable_token_index(
        text, 'git remote set-url origin "ssh://git@${GITHUB_SERVER_URL#https://}/${GITHUB_REPOSITORY}.git"',
    )
    create = _executable_token_index(text, 'git tag -a "$TAG" "$SOURCE_SHA"')
    push = _executable_token_index(text, 'git push origin "refs/tags/$TAG:refs/tags/$TAG"')
    restored_remote = _executable_token_index(
        text,
        'git remote set-url origin "https://github.com/${GITHUB_REPOSITORY}.git"',
        push + 1,
    )
    ref_readback = _executable_token_index(text, "/git/ref/tags/${TAG}", push + 1)
    object_readback = _executable_token_index(text, "/git/tags/${REMOTE_OBJECT_OID}", ref_readback + 1)
    outcome = _executable_token_index(text, "tag-mutation-outcome", object_readback + 1)
    post_readback = _executable_token_index(text, "--phase post_mutation", outcome + 1)
    key_removed = _executable_token_index(text, 'rm -f "$KEY_FILE"', post_readback + 1)
    finalization = _executable_token_index(text, '"tag-admit-$KIND-finalize"')
    if (
        min(
            pre_readback,
            admit_rc,
            admit_stable,
            intent_check,
            remote_absent,
            key_match,
            ssh_remote,
            create,
            push,
            restored_remote,
            ref_readback,
            object_readback,
            outcome,
            post_readback,
            key_removed,
            finalization,
        ) < 0
        or not (
            pre_readback < admit_rc
            and pre_readback < admit_stable
            and max(admit_rc, admit_stable) < intent_check
            and intent_check < remote_absent < key_match < ssh_remote < create <= push
            and push < restored_remote < ref_readback
            and ref_readback < object_readback < outcome < post_readback
            and post_readback < finalization < key_removed
        )
        or text.count("uses: actions/checkout@")
        != text.count("persist-credentials: false")
        or "verified-pre-push-local-admission" in text
        or "release_control.py --help" in text
    ):
        failures.append(
            f"{path.relative_to(ROOT)} is still a tag-controller placeholder: "
            "hosted pre-readback and both intents must precede the deploy-key create-only "
            "mutation; REST ref/object readback, mutation outcome, hosted post-readbacks "
            "and finalization must then remain ordered before the key is removed"
        )
    return failures


def verify_unique_release_tag_controller() -> list[str]:
    selection = RELEASE_WORKFLOWS["selection"]
    failures: list[str] = []
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        if path == selection:
            continue
        text = path.read_text(encoding="utf-8")
        for token in ("git tag -a", "git tag --annotate", "refs/tags/$TAG:refs/tags/$TAG"):
            if _executable_token_index(text, token) >= 0:
                failures.append(
                    f"{path.relative_to(ROOT)} contains release tag mutation outside "
                    f"the unique controller: {token}"
                )
    return failures


def verify_production_execution_isolation() -> list[str]:
    failures: list[str] = []
    production = RELEASE_WORKFLOWS["production"]
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        if re.search(r"runs-on\s*:[^\n]*\bprod-release\b", text):
            failures.append(
                f"{path.relative_to(ROOT)} must not target the retired prod-release runner label"
            )
    if not production.is_file():
        return failures + [".github/workflows/deploy-prod-auto.yml is required"]
    text = production.read_text(encoding="utf-8")
    failures += _verify_top_level_permissions(production, text, {"contents: read"})
    failures += _verify_dispatch_inputs(
        production,
        text,
        {
            "release_tag_admission_ref",
            "previous_active_released_ledger_ref",
            "rollback_readiness_ref",
        },
    )
    required_prod_runner = "runs-on: [self-hosted, macOS, ARM64]"
    if required_prod_runner not in text:
        failures.append(
            f"{production.relative_to(ROOT)} missing production isolation control: "
            f"{required_prod_runner}"
        )
    failures += _require_tokens(
        production,
        text,
        (
            "stable ReleaseTagAdmissionFact OCI @sha256 ref",
            "environment: production",
            "runs-on: [self-hosted, macOS, ARM64]",
            "packages: write",
            "attestations: read",
            "persist-credentials: false",
            "ProdActivationAdmissionFact",
            "release_control.py --store-root",
            "prod-admit",
            "prod-materialize-input",
            "stackctl.py deploy --target prod-hosted",
            "for stage in canary 5 20 50 100",
            "--from-candidate-digest",
            "--to-candidate-digest",
            "--service-factory-material",
            "--app-factory-material",
            "--hosted-receipt-readback",
            "--hosted-soak-readback",
        ),
        "qualified production transaction control",
    )
    failures += _forbid_tokens(
        production,
        text,
        (
            "pull-requests: read",
            "contents: write",
            "attestations: write",
            "verify_release_governance.py",
            "governance-receipt.json",
            "git tag -a",
            "build_sign_attest_once",
            "refs/heads/main",
            "github.ref_name",
            "github.sha",
            "latestQualified",
            "latest-qualified",
            "RELEASED_RELEASE_EVIDENCE_REF",
            "--release-evidence-ref",
            "--release-manifest",
            "fetch_mainline_release_artifact.py",
            "releaseEvidenceRef",
            "workflow_run:",
            "actions/upload-artifact@",
            "actions/download-artifact@",
            "mapfile",
            "readarray",
        ),
        "production selector, mutation, authority transport, or macOS-incompatible shell builtin",
    )
    if text.count("environment: production") < 2:
        failures.append(
            f"{production.relative_to(ROOT)} must apply production approval to admission and rollout jobs"
        )
    admit = _executable_token_index(text, "prod-admit")
    rollout = _executable_token_index(text, "stackctl.py deploy --target prod-hosted")
    if (
        admit < 0
        or rollout < 0
        or admit > rollout
        or any(
            token in text
            for token in (
                "pending-controller-output",
                "unreachable until all exact fact payloads are materialized",
                "transport must expose qualification and candidate material fact payloads",
            )
        )
    ):
        failures.append(
            f"{production.relative_to(ROOT)} is still a production placeholder: "
            "qualified_prod must materialize one exact ProdActivationAdmissionFact before stackctl"
        )
    return failures


def verify_release_attestation_controls() -> list[str]:
    failures: list[str] = []
    service = WORKFLOWS / "service_pipeline.yml"
    app = WORKFLOWS / "app_pipeline.yml"
    verifier = ROOT / "quwoquan_ops/cli/prod/oci_supply_chain.py"
    service_text = service.read_text(encoding="utf-8")
    app_text = app.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")
    failures += _require_tokens(
        service,
        service_text,
        (
            "id-token: write",
            "attestations: write",
            ATTEST_ACTION,
            "sbom-path:",
            "push-to-registry: true",
            "oci_supply_chain.py extract-sbom",
            "--signer-workflow",
        ),
        "signed service material control",
    )
    failures += _require_tokens(
        app,
        app_text,
        (
            "environment: release-signing",
            "sbom: true",
            "provenance: mode=max",
            "app_evidence_ref:",
            "android_artifact_digest:",
            "ios_artifact_digest:",
            "web_artifact_digest:",
        ),
        "signed App material control",
    )
    failures += _require_tokens(
        verifier,
        verifier_text,
        (
            '"--bundle-from-oci"',
            '"--signer-workflow"',
            '"--cert-oidc-issuer"',
            'OIDC_ISSUER = "https://token.actions.githubusercontent.com"',
            '"{{json .SBOM}}"',
            '"{{json .Provenance}}"',
        ),
        "cryptographic verification control",
    )
    return failures


def verify_codeowners() -> list[str]:
    if not CODEOWNERS.is_file():
        return [".github/CODEOWNERS is required"]
    declared: set[str] = set()
    for raw_line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or not all(owner.startswith("@") for owner in parts[1:]):
            return [f".github/CODEOWNERS has an invalid rule: {raw_line}"]
        declared.add(parts[0])
    missing = sorted(REQUIRED_CODEOWNER_PATHS - declared)
    return [f".github/CODEOWNERS missing critical path rule: {path}" for path in missing]


def main() -> int:
    failures = [
        *verify_action_pins(),
        *verify_codeowners(),
        *verify_release_qualification_controls(),
        *verify_release_tag_selection_controls(),
        *verify_unique_release_tag_controller(),
        *verify_production_execution_isolation(),
        *verify_release_attestation_controls(),
    ]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "OK: GitHub release workflows are immutable, least-privilege, "
        "single-controller, exact-evidence transactions with CODEOWNERS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

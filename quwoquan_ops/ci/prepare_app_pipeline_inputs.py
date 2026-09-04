"""Prepare one fresh, source-bound hosted App package input transaction."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_app.scripts.device.build_launcher_handoff import (
    materialize_runtime_config_trust_envelope,
)
from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    resolve_cocoapods_executable,
)
from quwoquan_ops.cli.lib.app_identity import (
    AppIdentityError,
    build_profile_for_environment,
    resolve_build_product,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
    load_launch_manifest_contract,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import (
    decode_keyring,
)
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_network_command import (
    run_managed_subprocess,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    load_active_dependency_bundle,
)

PROD_TRUSTED_PUBLIC_KEYS_JSON_ENV = (
    "QWQ_APP_RUNTIME_CONFIG_PROD_TRUSTED_PUBLIC_KEYS_JSON"
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_TREE_DIGEST = re.compile(r"^sha1:[0-9a-f]{40}$")
_ATTEMPT_ID = re.compile(r"^[0-9a-f]{32}$")
_DEPENDENCY_SYNC_TIMEOUT_SECONDS = 20 * 60


class PipelinePreparationError(RuntimeError):
    """Typed fail-closed hosted candidate preparation blocker."""


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    git_sha: str
    tree_digest: str


@dataclass(frozen=True, slots=True)
class PreparationRequest:
    build_product_id: str
    environment: str
    target: str
    expected_source_git_sha: str
    work_root: Path


@dataclass(frozen=True, slots=True)
class PreparedAppPipelineInputs:
    transaction_root: Path
    output_root: Path
    runtime_config_trust_path: Path | None
    dependency_attempt_id: str
    source_git_sha: str
    source_tree_digest: str
    flutter_version: str
    flutter_command_resolution_digest: str
    cocoapods_executable: str

    def github_outputs(self) -> dict[str, str]:
        return {
            "transaction_root": str(self.transaction_root),
            "qwq_output_root": str(self.output_root),
            "runtime_config_trust_path": str(self.runtime_config_trust_path or ""),
            "dependency_attempt_id": self.dependency_attempt_id,
            "source_git_sha": self.source_git_sha,
            "source_tree_digest": self.source_tree_digest,
            "flutter_version": self.flutter_version,
            "flutter_command_resolution_digest": (
                self.flutter_command_resolution_digest
            ),
            "cocoapods_executable": self.cocoapods_executable,
        }


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "git command failed"
        raise PipelinePreparationError(
            f"APP.PIPELINE.source_identity_unavailable: {detail}"
        )
    return result.stdout.strip()


def _capture_source_identity() -> SourceIdentity:
    identity = SourceIdentity(
        git_sha=_git("rev-parse", "HEAD"),
        tree_digest=f"sha1:{_git('rev-parse', 'HEAD^{tree}')}",
    )
    if not _GIT_SHA.fullmatch(identity.git_sha) or not _TREE_DIGEST.fullmatch(
        identity.tree_digest
    ):
        raise PipelinePreparationError("APP.PIPELINE.source_identity_invalid")
    return identity


def _require_clean_checkout() -> None:
    if _git("status", "--porcelain", "--untracked-files=all"):
        raise PipelinePreparationError("APP.PIPELINE.checkout_not_clean")


def _resolve_flutter() -> dict[str, str]:
    try:
        identity = resolved_flutter_identity(dict(os.environ))
    except FacadeError as error:
        raise PipelinePreparationError(
            f"APP.PIPELINE.flutter_identity_invalid: {error}"
        ) from error
    return {str(key): str(value) for key, value in identity.items()}


def _resolve_pod() -> str:
    try:
        return resolve_cocoapods_executable(
            str(os.environ.get("QWQ_COCOAPODS_EXECUTABLE") or "")
        )
    except AppDependencyToolchainError as error:
        raise PipelinePreparationError(
            f"APP.PIPELINE.cocoapods_identity_invalid: {error}"
        ) from error


def _write_private(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _profile_keyring(build_profile: str, private_root: Path) -> dict[str, str]:
    if build_profile == "nonprod":
        signing = prepare_local_app_runtime_config_signing(REPO_ROOT)
        return decode_keyring(signing.trusted_public_keys_path.read_bytes())
    if build_profile != "prod":
        raise PipelinePreparationError(
            f"APP.PIPELINE.trust_profile_invalid: {build_profile}"
        )
    raw = str(os.environ.get(PROD_TRUSTED_PUBLIC_KEYS_JSON_ENV) or "").strip()
    if not raw:
        raise PipelinePreparationError("APP.PIPELINE.prod_trust_keyring_missing")
    try:
        keyring = decode_keyring(raw.encode("utf-8"))
    except ValueError as error:
        raise PipelinePreparationError(
            f"APP.PIPELINE.prod_trust_keyring_invalid: {error}"
        ) from error
    # Persist the protected workflow input only under this fresh transaction.
    _write_private(
        private_root / "prod-trusted-public-keys.json",
        json.dumps(
            keyring, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
    )
    return keyring


def _materialize_profile_trust(build_profile: str, output: Path) -> None:
    output.parent.mkdir(parents=True, mode=0o700)
    keyring = _profile_keyring(build_profile, output.parents[2] / "protected")
    envelope = build_runtime_config_trust_envelope(build_profile, keyring)
    materialize_runtime_config_trust_envelope(
        envelope,
        str(output),
        load_launch_manifest_contract(),
    )


def _captured_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _dependency_sync_stderr_path(result_path: Path) -> Path:
    return result_path.with_suffix(".stderr.log")


def _persist_dependency_sync_diagnostics(
    *, result_path: Path, stdout: str, stderr: str
) -> None:
    _write_private(result_path, stdout.encode("utf-8"))
    if stderr:
        _write_private(
            _dependency_sync_stderr_path(result_path),
            stderr.encode("utf-8"),
        )


def _run_dependency_sync(
    *, environment: dict[str, str], result_path: Path
) -> dict[str, object]:
    command = [
        sys.executable,
        str(REPO_ROOT / "quwoquan_ops/cli/stackctl.py"),
        "--output-format",
        "json",
        "app-dependency-sync",
    ]
    try:
        result = run_managed_subprocess(
            command,
            cwd=REPO_ROOT,
            env=environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_DEPENDENCY_SYNC_TIMEOUT_SECONDS,
            on_stderr=lambda chunk: print(chunk, file=sys.stderr, end="", flush=True),
        )
    except subprocess.TimeoutExpired as error:
        stdout = _captured_text(error.stdout)
        stderr = _captured_text(error.stderr)
        _persist_dependency_sync_diagnostics(
            result_path=result_path,
            stdout=stdout,
            stderr=stderr,
        )
        detail = (stderr or stdout).strip().splitlines()
        first = detail[0] if detail else "stackctl returned no diagnostic output"
        raise PipelinePreparationError(
            "APP.PIPELINE.dependency_sync_timeout: "
            f"timeoutSeconds={_DEPENDENCY_SYNC_TIMEOUT_SECONDS}; diagnostic={first}"
        ) from error
    _persist_dependency_sync_diagnostics(
        result_path=result_path,
        stdout=result.stdout,
        stderr=result.stderr or "",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = (result.stderr or result.stdout).strip().splitlines()
        first = detail[0] if detail else "stackctl returned no JSON"
        raise PipelinePreparationError(
            f"APP.PIPELINE.dependency_sync_result_invalid: {first}"
        ) from error
    if not isinstance(payload, dict):
        raise PipelinePreparationError(
            "APP.PIPELINE.dependency_sync_result_invalid: result is not an object"
        )
    if result.returncode != 0 or payload.get("exitCode") != 0:
        details = payload.get("details")
        first = (
            str(details[0])
            if isinstance(details, list) and details
            else f"processExit={result.returncode}"
        )
        raise PipelinePreparationError(f"APP.PIPELINE.dependency_sync_blocked: {first}")
    return payload


def _load_active_bundle(repo_root: Path) -> Any:
    return load_active_dependency_bundle(repo_root=repo_root)


@contextmanager
def _temporary_environment(values: Mapping[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _validate_selection(request: PreparationRequest) -> str:
    try:
        product = resolve_build_product(request.build_product_id)
        contract = load_launch_manifest_contract()
        target_environment = contract["target_environment"].get(request.target)
        environment_profile = build_profile_for_environment(request.environment)
    except (AppIdentityError, KeyError, TypeError, ValueError) as error:
        raise PipelinePreparationError(
            f"APP.PIPELINE.selection_invalid: {error}"
        ) from error
    expected_profile = product.build_profile
    if (
        target_environment != request.environment
        or (expected_profile != "shared" and environment_profile != expected_profile)
        or (
            expected_profile == "shared"
            and (request.environment, request.target) != ("prod", "prod-hosted")
        )
        or (expected_profile == "prod" and request.target != "prod-hosted")
    ):
        raise PipelinePreparationError(
            "APP.PIPELINE.selection_invalid: product/profile/environment/target mismatch"
        )
    return expected_profile


def _fresh_transaction_root(request: PreparationRequest, profile: str) -> Path:
    work_root = request.work_root.expanduser()
    if not work_root.is_absolute():
        raise PipelinePreparationError("APP.PIPELINE.work_root_invalid")
    resolved_repo = REPO_ROOT.resolve()
    resolved_work = work_root.resolve(strict=False)
    if resolved_work == resolved_repo or resolved_repo in resolved_work.parents:
        raise PipelinePreparationError("APP.PIPELINE.work_root_inside_repository")
    root = resolved_work / profile / request.build_product_id
    if root.exists() or root.is_symlink():
        raise PipelinePreparationError("APP.PIPELINE.transaction_root_must_be_fresh")
    root.mkdir(parents=True, mode=0o700)
    return root


def _dependency_attempt(payload: Mapping[str, object]) -> str:
    activation = payload.get("activation")
    if not isinstance(activation, Mapping) or activation.get("status") != "committed":
        raise PipelinePreparationError("APP.PIPELINE.dependency_activation_missing")
    attempt = str(activation.get("attemptId") or "")
    if not _ATTEMPT_ID.fullmatch(attempt):
        raise PipelinePreparationError(
            "APP.PIPELINE.dependency_activation_identity_invalid"
        )
    return attempt


def prepare(request: PreparationRequest) -> PreparedAppPipelineInputs:
    profile = _validate_selection(request)
    expected_sha = request.expected_source_git_sha.strip()
    if not _GIT_SHA.fullmatch(expected_sha):
        raise PipelinePreparationError("APP.PIPELINE.expected_source_invalid")
    transaction_root = _fresh_transaction_root(request, profile)
    try:
        _require_clean_checkout()
        before_source = _capture_source_identity()
        if before_source.git_sha != expected_sha:
            raise PipelinePreparationError("APP.PIPELINE.source_identity_mismatch")
        before_flutter = _resolve_flutter()
        pod = _resolve_pod()
        output_root = transaction_root / "qwq-output"
        output_root.mkdir(mode=0o700)

        artifact_trust: Path | None = None
        if profile in {"nonprod", "prod"}:
            artifact_trust = (
                transaction_root
                / "runtime-config/qwq_runtime/runtime-config-trust.json"
            )
            _materialize_profile_trust(profile, artifact_trust)

        if profile == "nonprod":
            sync_trust = artifact_trust
        else:
            sync_trust = (
                transaction_root / "dependency-runtime-config/nonprod/qwq_runtime/"
                "runtime-config-trust.json"
            )
            _materialize_profile_trust("nonprod", sync_trust)
        if sync_trust is None:
            raise PipelinePreparationError("APP.PIPELINE.sync_trust_missing")

        process_environment = dict(os.environ)
        process_environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "QWQ_OUTPUT_ROOT": str(output_root),
                "QWQ_REAL_FLUTTER": str(before_flutter["executable"]),
                "QWQ_COCOAPODS_EXECUTABLE": pod,
                "QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT": str(sync_trust.parents[1]),
            }
        )
        payload = _run_dependency_sync(
            environment=process_environment,
            result_path=transaction_root / "app-dependency-sync-result.json",
        )
        attempt = _dependency_attempt(payload)
        with _temporary_environment(process_environment):
            active = _load_active_bundle(REPO_ROOT)
        if str(active.active.get("attemptId") or "") != attempt:
            raise PipelinePreparationError(
                "APP.PIPELINE.dependency_active_attempt_mismatch"
            )
        if active.active.get("flutterVersion") != before_flutter.get(
            "flutterVersion"
        ) or active.active.get("flutterCommandResolutionDigest") != before_flutter.get(
            "commandResolutionDigest"
        ):
            raise PipelinePreparationError(
                "APP.PIPELINE.dependency_toolchain_binding_mismatch"
            )
        after_source = _capture_source_identity()
        after_flutter = _resolve_flutter()
        _require_clean_checkout()
        if after_source != before_source or after_flutter != before_flutter:
            raise PipelinePreparationError(
                "APP.PIPELINE.source_or_toolchain_drift_during_preparation"
            )
        return PreparedAppPipelineInputs(
            transaction_root=transaction_root,
            output_root=output_root,
            runtime_config_trust_path=artifact_trust,
            dependency_attempt_id=attempt,
            source_git_sha=before_source.git_sha,
            source_tree_digest=before_source.tree_digest,
            flutter_version=str(before_flutter["flutterVersion"]),
            flutter_command_resolution_digest=str(
                before_flutter["commandResolutionDigest"]
            ),
            cocoapods_executable=pod,
        )
    except PipelinePreparationError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise PipelinePreparationError(
            f"APP.PIPELINE.input_preparation_blocked: {error}"
        ) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-product-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-source-git-sha", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    return parser


def _append_github_outputs(path: Path, values: Mapping[str, str]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise PipelinePreparationError(
                    f"APP.PIPELINE.github_output_invalid: {key}"
                )
            stream.write(f"{key}={value}\n")


def main() -> int:
    args = _parser().parse_args()
    try:
        prepared = prepare(
            PreparationRequest(
                build_product_id=args.build_product_id,
                environment=args.environment,
                target=args.target,
                expected_source_git_sha=args.expected_source_git_sha,
                work_root=args.work_root,
            )
        )
        _append_github_outputs(args.github_output, prepared.github_outputs())
    except PipelinePreparationError as error:
        print(f"::error::GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(
        "[app-pipeline-inputs] prepared "
        f"product={args.build_product_id} attempt={prepared.dependency_attempt_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fresh hosted App candidate input transaction contract."""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-001

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from quwoquan_ops.ci import materialize_app_pipeline_web_release as web_release
from quwoquan_ops.ci import prepare_app_pipeline_inputs as subject

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app_pipeline.yml"
DELIVERY_WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"
SHA256_A = "sha256:" + "a" * 64
SOURCE = subject.SourceIdentity(
    git_sha="1" * 40,
    tree_digest="sha1:" + "2" * 40,
)
FLUTTER = {
    "executable": "/toolchain/flutter",
    "flutterVersion": "3.47.0",
    "commandResolutionDigest": SHA256_A,
}


def _stub_stable_transaction(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> None:
    monkeypatch.setattr(subject, "_capture_source_identity", lambda: SOURCE)
    monkeypatch.setattr(subject, "_require_clean_checkout", lambda: None)
    monkeypatch.setattr(subject, "_resolve_flutter", lambda: dict(FLUTTER))
    monkeypatch.setattr(subject, "_resolve_pod", lambda: "/toolchain/pod-1.16.2")

    def materialize(profile: str, output: Path) -> None:
        events.append(f"trust:{profile}")
        output.parent.mkdir(parents=True)
        output.write_text(
            json.dumps({"schema": "app-runtime-config-trust", "buildProfile": profile}),
            encoding="utf-8",
        )
        output.chmod(0o600)

    def sync(*, environment: dict[str, str], result_path: Path) -> dict[str, object]:
        events.append("sync")
        assert environment["QWQ_COCOAPODS_EXECUTABLE"] == "/toolchain/pod-1.16.2"
        assert Path(environment["QWQ_OUTPUT_ROOT"]).name == "qwq-output"
        trust_root = Path(environment["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"])
        assert (trust_root / "qwq_runtime/runtime-config-trust.json").is_file()
        payload: dict[str, object] = {
            "exitCode": 0,
            "activation": {"status": "committed", "attemptId": "b" * 32},
        }
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def load_active(_repo_root: Path) -> SimpleNamespace:
        events.append("active")
        return SimpleNamespace(
            active={
                "attemptId": "b" * 32,
                "flutterVersion": FLUTTER["flutterVersion"],
                "flutterCommandResolutionDigest": FLUTTER["commandResolutionDigest"],
            }
        )

    monkeypatch.setattr(subject, "_materialize_profile_trust", materialize)
    monkeypatch.setattr(subject, "_run_dependency_sync", sync)
    monkeypatch.setattr(subject, "_load_active_bundle", load_active)


def test_dependency_sync_timeout_is_bounded_typed_and_preserves_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def timeout_run(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured["timeout"] = kwargs.get("timeout")
        captured["stderr"] = kwargs.get("stderr")
        captured["on_stderr"] = kwargs.get("on_stderr")
        raise subprocess.TimeoutExpired(
            command,
            timeout=kwargs["timeout"],
            output=b"partial stackctl stdout\n",
            stderr=b"app-dependency-sync warning\nsecond diagnostic line\n",
        )

    monkeypatch.setattr(subject, "run_managed_subprocess", timeout_run)
    result_path = tmp_path / "app-dependency-sync-result.json"

    with pytest.raises(
        subject.PipelinePreparationError,
        match=(
            r"^APP\.PIPELINE\.dependency_sync_timeout: "
            r"timeoutSeconds=1200; diagnostic=app-dependency-sync warning$"
        ),
    ):
        subject._run_dependency_sync(
            environment={"PYTHONDONTWRITEBYTECODE": "1"},
            result_path=result_path,
        )

    assert captured["timeout"] == subject._DEPENDENCY_SYNC_TIMEOUT_SECONDS
    assert captured["stderr"] == subprocess.PIPE
    assert callable(captured["on_stderr"])
    assert captured["command"] == [
        subject.sys.executable,
        str(subject.REPO_ROOT / "quwoquan_ops/cli/stackctl.py"),
        "--output-format",
        "json",
        "app-dependency-sync",
    ]
    assert result_path.read_text(encoding="utf-8") == "partial stackctl stdout\n"
    stderr_path = result_path.with_suffix(".stderr.log")
    assert stderr_path.read_text(encoding="utf-8") == (
        "app-dependency-sync warning\nsecond diagnostic line\n"
    )
    assert result_path.stat().st_mode & 0o777 == 0o600
    assert stderr_path.stat().st_mode & 0o777 == 0o600


def test_mobile_preparation_orders_profile_trust_sync_and_fresh_active_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _stub_stable_transaction(monkeypatch, events)

    prepared = subject.prepare(
        subject.PreparationRequest(
            build_product_id="android-nonprod-apk",
            environment="alpha",
            target="alpha-local",
            expected_source_git_sha=SOURCE.git_sha,
            work_root=tmp_path / "hosted-inputs",
        )
    )

    assert events == ["trust:nonprod", "sync", "active"]
    expected_root = (tmp_path / "hosted-inputs/nonprod/android-nonprod-apk").resolve()
    assert prepared.transaction_root == expected_root
    assert prepared.output_root == expected_root / "qwq-output"
    assert prepared.runtime_config_trust_path == (
        expected_root / "runtime-config/qwq_runtime/runtime-config-trust.json"
    )
    assert prepared.dependency_attempt_id == "b" * 32
    assert prepared.source_git_sha == SOURCE.git_sha


def test_prod_preparation_uses_isolated_prod_artifact_trust_and_nonprod_sync_trust(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _stub_stable_transaction(monkeypatch, events)
    monkeypatch.setenv(
        subject.PROD_TRUSTED_PUBLIC_KEYS_JSON_ENV,
        '{"prod-key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}',
    )

    prepared = subject.prepare(
        subject.PreparationRequest(
            build_product_id="ios-prod-app",
            environment="prod",
            target="prod-hosted",
            expected_source_git_sha=SOURCE.git_sha,
            work_root=tmp_path / "hosted-inputs",
        )
    )

    assert events == ["trust:prod", "trust:nonprod", "sync", "active"]
    assert "/prod/ios-prod-app/" in str(prepared.runtime_config_trust_path)


def test_existing_transaction_root_blocks_without_old_cache_or_receipt_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _stub_stable_transaction(monkeypatch, events)
    stale = tmp_path / "hosted-inputs/nonprod/android-nonprod-apk"
    stale.mkdir(parents=True)
    (stale / "old-receipt.json").write_text("{}", encoding="utf-8")

    with pytest.raises(subject.PipelinePreparationError, match="must_be_fresh"):
        subject.prepare(
            subject.PreparationRequest(
                build_product_id="android-nonprod-apk",
                environment="alpha",
                target="alpha-local",
                expected_source_git_sha=SOURCE.git_sha,
                work_root=tmp_path / "hosted-inputs",
            )
        )

    assert events == []
    assert (stale / "old-receipt.json").is_file()


def test_prod_keyring_is_required_and_materialized_as_private_canonical_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(subject.PROD_TRUSTED_PUBLIC_KEYS_JSON_ENV, raising=False)
    with pytest.raises(subject.PipelinePreparationError, match="keyring_missing"):
        subject._profile_keyring("prod", tmp_path / "missing")

    monkeypatch.setenv(
        subject.PROD_TRUSTED_PUBLIC_KEYS_JSON_ENV,
        '{"prod-key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}',
    )
    keyring = subject._profile_keyring("prod", tmp_path / "protected")

    assert set(keyring) == {"prod-key"}
    materialized = tmp_path / "protected/prod-trusted-public-keys.json"
    assert materialized.is_file()
    assert materialized.stat().st_mode & 0o777 == 0o600


def test_source_drift_after_active_readback_blocks_prepared_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _stub_stable_transaction(monkeypatch, events)
    identities = iter([SOURCE, subject.SourceIdentity("3" * 40, "sha1:" + "4" * 40)])
    monkeypatch.setattr(subject, "_capture_source_identity", lambda: next(identities))

    with pytest.raises(subject.PipelinePreparationError, match="drift_during"):
        subject.prepare(
            subject.PreparationRequest(
                build_product_id="android-nonprod-apk",
                environment="alpha",
                target="alpha-local",
                expected_source_git_sha=SOURCE.git_sha,
                work_root=tmp_path / "hosted-inputs",
            )
        )

    assert events == ["trust:nonprod", "sync", "active"]


@pytest.mark.parametrize(
    ("product", "environment", "target"),
    [
        ("android-nonprod-apk", "prod", "prod-hosted"),
        ("android-prod-apk", "alpha", "alpha-local"),
        ("ios-nonprod-app", "beta", "gamma-local"),
        ("web-shared", "gamma", "gamma-local"),
    ],
)
def test_profile_and_target_selection_fail_closed(
    tmp_path: Path,
    product: str,
    environment: str,
    target: str,
) -> None:
    with pytest.raises(subject.PipelinePreparationError, match="selection_invalid"):
        subject.prepare(
            subject.PreparationRequest(
                build_product_id=product,
                environment=environment,
                target=target,
                expected_source_git_sha=SOURCE.git_sha,
                work_root=tmp_path / "hosted-inputs",
            )
        )


def test_web_preparation_has_no_mobile_trust_output_but_keeps_fresh_dependency_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _stub_stable_transaction(monkeypatch, events)

    prepared = subject.prepare(
        subject.PreparationRequest(
            build_product_id="web-shared",
            environment="prod",
            target="prod-hosted",
            expected_source_git_sha=SOURCE.git_sha,
            work_root=tmp_path / "hosted-inputs",
        )
    )

    assert events == ["trust:nonprod", "sync", "active"]
    assert prepared.runtime_config_trust_path is None


def test_hosted_workflow_passes_exact_fresh_outputs_to_every_package() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.load(source, Loader=yaml.BaseLoader)
    product = document["jobs"]["product"]
    steps = product["steps"]

    assert product["runs-on"] == "macos-latest"
    assert int(product["timeout-minutes"]) == 30
    delivery_document = yaml.load(
        DELIVERY_WORKFLOW.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    delivery_packaging = delivery_document["jobs"]["quwoquan_service_packaging"]
    assert int(delivery_packaging["timeout-minutes"]) == 30
    assert subject._DEPENDENCY_SYNC_TIMEOUT_SECONDS < min(
        int(product["timeout-minutes"]),
        int(delivery_packaging["timeout-minutes"]),
    ) * 60
    prepare_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "strict_inputs"
    )
    package_index = next(
        index
        for index, step in enumerate(steps)
        if "stackctl.py --output-format json package" in str(step.get("run", ""))
    )
    assert prepare_index < package_index
    prepare_step = steps[prepare_index]
    assert "prepare_app_pipeline_inputs.py" in prepare_step["run"]
    assert "--build-product-id" in prepare_step["run"]
    assert "--expected-source-git-sha" in prepare_step["run"]
    assert "--environment" in prepare_step["run"]
    assert "--target" in prepare_step["run"]

    package_step = steps[package_index]
    assert package_step["env"]["QWQ_OUTPUT_ROOT"] == (
        "${{ steps.strict_inputs.outputs.qwq_output_root }}"
    )
    assert package_step["env"]["QWQ_APP_RUNTIME_CONFIG_TRUST_PATH"] == (
        "${{ steps.strict_inputs.outputs.runtime_config_trust_path }}"
    )
    assert package_step["env"]["QWQ_COCOAPODS_EXECUTABLE"] == (
        "${{ steps.strict_inputs.outputs.cocoapods_executable }}"
    )
    assert (
        "QWQ_APP_RUNTIME_CONFIG_PROD_TRUSTED_PUBLIC_KEYS_JSON"
        in document["on"]["workflow_call"]["secrets"]
    )
    assert "actions/cache" not in prepare_step["run"]


def _web_result(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    artifact = tmp_path / "web-artifact"
    artifact.mkdir()
    (artifact / "index.html").write_text(
        '<html lang="zh-CN"><head><meta charset="utf-8"></head></html>',
        encoding="utf-8",
    )
    (artifact / "main.dart.js").write_text("main();", encoding="utf-8")
    (artifact / "flutter_service_worker.js").write_text("worker();", encoding="utf-8")
    (artifact / "qwq_bootstrap.css").write_text(":root{}", encoding="utf-8")
    (artifact / "qwq_bootstrap.js").write_text("bootstrap();", encoding="utf-8")
    (artifact / "manifest.json").write_text(
        json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
        encoding="utf-8",
    )
    fonts = artifact / "assets"
    font = fonts / "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf"
    font.parent.mkdir(parents=True)
    font.write_bytes(b"font")
    (fonts / "FontManifest.json").write_text(
        json.dumps(
            [
                {
                    "family": "Noto Sans SC",
                    "fonts": [
                        {"asset": "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf"}
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    product = web_release.resolve_build_product("web-shared")
    manifest: dict[str, object] = {
        "schema": "app-artifact-manifest",
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "artifactFormat": product.artifact_format,
        "distributionClass": product.distribution_class,
        "promotable": True,
        "artifactDigest": web_release.artifact_digest(artifact),
    }
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    result = tmp_path / "stackctl-result.json"
    result.write_text(
        json.dumps({"exitCode": 0, "attemptDir": str(attempt), "manifest": manifest}),
        encoding="utf-8",
    )
    return result, artifact, manifest


def test_web_release_materializer_binds_exact_validated_artifact_and_closed_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, artifact, manifest = _web_result(tmp_path)
    calls: list[dict[str, object]] = []

    def validate(**kwargs: object) -> SimpleNamespace:
        calls.append(dict(kwargs))
        return SimpleNamespace(artifact_path=artifact)

    monkeypatch.setattr(web_release, "validate_app_artifact_build_receipt", validate)
    output = tmp_path / "web-release.json"

    rendered = web_release.materialize(result_path=result, output_path=output)

    content_digest = web_release.web_official_content_digest(artifact)
    assert calls == [
        {
            "attempt_dir": tmp_path / "attempt",
            "expected_build_product_id": "web-shared",
            "expected_manifest": manifest,
        }
    ]
    assert rendered == {
        "schema": "client-app.web.official-release",
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
    }
    assert json.loads(output.read_text(encoding="utf-8")) == rendered
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("mutation", "blocker"),
    [
        (lambda result: result.update(exitCode=2), "result_not_successful"),
        (
            lambda result: result["manifest"].update(buildProductId="ios-prod-app"),
            "manifest_invalid",
        ),
        (
            lambda result: result["manifest"].update(platform="android"),
            "manifest_invalid",
        ),
    ],
)
def test_web_release_materializer_rejects_noncanonical_stackctl_result(
    tmp_path: Path,
    mutation: object,
    blocker: str,
) -> None:
    result, _artifact, _manifest = _web_result(tmp_path)
    payload = json.loads(result.read_text(encoding="utf-8"))
    mutation(payload)
    result.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(web_release.WebReleaseMaterializationError, match=blocker):
        web_release.materialize(
            result_path=result,
            output_path=tmp_path / "must-not-exist.json",
        )

    assert not (tmp_path / "must-not-exist.json").exists()


def test_web_release_materializer_preserves_existing_output_and_validator_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, artifact, _manifest = _web_result(tmp_path)
    monkeypatch.setattr(
        web_release,
        "validate_app_artifact_build_receipt",
        lambda **_kwargs: SimpleNamespace(artifact_path=artifact),
    )
    output = tmp_path / "web-release.json"
    web_release.materialize(result_path=result, output_path=output)
    before = output.read_bytes()

    with pytest.raises(
        web_release.WebReleaseMaterializationError, match="output_exists"
    ):
        web_release.materialize(result_path=result, output_path=output)
    assert output.read_bytes() == before

    output.unlink()
    monkeypatch.setattr(
        web_release,
        "validate_app_artifact_build_receipt",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("receipt drifted")),
    )
    with pytest.raises(
        web_release.WebReleaseMaterializationError, match="receipt drifted"
    ):
        web_release.materialize(result_path=result, output_path=output)
    assert not output.exists()


@pytest.mark.parametrize(
    "invalid_artifact",
    ("embedded-runtime", "missing-bootstrap", "invalid-index", "invalid-pwa"),
)
def test_web_release_materializer_rejects_nonofficial_existing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_artifact: str,
) -> None:
    result, artifact, _manifest = _web_result(tmp_path)
    monkeypatch.setattr(
        web_release,
        "validate_app_artifact_build_receipt",
        lambda **_kwargs: SimpleNamespace(artifact_path=artifact),
    )
    if invalid_artifact == "embedded-runtime":
        (artifact / "runtime-config-trust.json").write_text("{}", encoding="utf-8")
    elif invalid_artifact == "missing-bootstrap":
        (artifact / "qwq_bootstrap.js").unlink()
    elif invalid_artifact == "invalid-index":
        (artifact / "index.html").write_text("<html></html>", encoding="utf-8")
    else:
        (artifact / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(
        web_release.WebReleaseMaterializationError,
        match="web_release_artifact_invalid",
    ):
        web_release.materialize(
            result_path=result,
            output_path=tmp_path / "must-not-exist.json",
        )
    assert not (tmp_path / "must-not-exist.json").exists()


def test_workflow_materializes_web_release_before_explicit_collector_input() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.load(workflow, Loader=yaml.BaseLoader)
    package_step = next(
        step
        for step in document["jobs"]["product"]["steps"]
        if "stackctl.py --output-format json package" in str(step.get("run", ""))
    )
    run = package_step["run"]

    assert run.count("materialize_app_pipeline_web_release.py") == 1
    assert 'if [ "${{ matrix.buildProductId }}" = web-shared ]; then' in run
    assert '--result "$RESULT" --output "$WEB_RELEASE_MANIFEST"' in run
    assert 'COLLECT_ARGS+=(--web-release-manifest "$WEB_RELEASE_MANIFEST")' in run
    assert run.index("materialize_app_pipeline_web_release.py") < run.index(
        "collect_stackctl_app_shard.py"
    )
    assert "client-app.web.official-release" not in workflow
    assert "launcher-handoff" not in workflow
    assert "flutter build" not in workflow

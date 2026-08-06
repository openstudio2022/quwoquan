from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import startup_attempt_receipt as subject


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _oci_manifest(
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    images = {
        "api-edge": {
            "ref": "quwoquan/api-edge:build",
            "imageDigest": "sha256:" + "1" * 64,
        },
        "provider-protocol-substitute": {
            "buildInputDigest": "sha256:" + "2" * 64,
            "ref": "quwoquan/provider-protocol-substitute:build",
            "imageDigest": "sha256:" + "3" * 64,
        },
        "sms-provider-substitute": {
            "buildInputDigest": "sha256:" + "4" * 64,
            "ref": "quwoquan/sms-provider-substitute:build",
            "imageDigest": "sha256:" + "5" * 64,
        },
    }
    return {
        "schema": "stackctl-package-oci-images",
        "environment": environment,
        "target": target,
        "configurationDigest": "sha256:" + "c" * 64,
        "buildInputDigest": "sha256:" + "6" * 64,
        "imageDigest": _digest_json(images),
        "images": images,
    }


def _composition(
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return subject.image_composition_from_candidate_oci(
        _oci_manifest(environment=environment, target=target),
        expected_environment=environment,
        expected_target=target,
    )


def _active_candidate_files(
    tmp_path: Path,
    *,
    manifest: dict[str, object] | None = None,
    baseline_id: str = "sha256:" + "b" * 64,
) -> tuple[Path, Path, Path, dict[str, object]]:
    candidate_root = tmp_path / "candidate"
    oci_path = candidate_root / "packages/runtime-shared/oci-images.json"
    oci_path.parent.mkdir(parents=True)
    oci = manifest or _oci_manifest()
    oci_path.write_text(json.dumps(oci), encoding="utf-8")
    active_path = tmp_path / "active-runtime-candidate.json"
    active_path.write_text(
        json.dumps(
            {
                "schema": subject.ACTIVE_CANDIDATE_SCHEMA,
                "candidateType": "runtime-full",
                "target": str(oci["target"]),
                "baselineId": baseline_id,
                "candidateDir": str(candidate_root),
            }
        ),
        encoding="utf-8",
    )
    candidate = {
        "baselineId": baseline_id,
        "runtimeConfigDigest": oci["configurationDigest"],
        "buildInputDigest": oci["buildInputDigest"],
        "imageDigest": oci["imageDigest"],
    }
    return active_path, candidate_root, oci_path, candidate


def test_startup_attempt_has_atomic_transactional_lifecycle(tmp_path: Path) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    run_root = tmp_path / "env/alpha/runs/up-alpha"
    composition = _composition()
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "attempt_id": "up-alpha",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "observability_log_sink_digest": "sha256:" + "e" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
        "run_root": str(run_root),
    }

    with (
        mock.patch.object(
            subject,
            "startup_attempt_path",
            return_value=receipt_path,
        ),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        prepared = subject.transition_startup_attempt(status="prepared", **common)
        partial = subject.transition_startup_attempt(status="partial", **common)
        running = subject.transition_startup_attempt(status="running", **common)
        stopped = subject.transition_startup_attempt(status="stopped", **common)

    assert [prepared["status"], partial["status"], running["status"], stopped["status"]] == [
        "prepared",
        "partial",
        "running",
        "stopped",
    ]
    assert stopped["composeProject"] == "quwoquan_alpha_release"
    assert stopped["providerRuntimeDigest"] == "sha256:" + "d" * 64
    assert stopped["observabilityLogSinkDigest"] == "sha256:" + "e" * 64
    assert stopped["imageComposition"] == _composition()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == stopped
    assert json.loads(
        (
            receipt_path.parent
            / "workloads/content-release/startup_attempt.json"
        ).read_text(encoding="utf-8")
    ) == stopped
    assert json.loads(
        (run_root / "startup_attempt.json").read_text(encoding="utf-8")
    ) == stopped
    assert not list(receipt_path.parent.glob("*.tmp"))


def test_partial_cleanup_failure_remains_partial_and_keeps_original_error(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    composition = _composition(environment="gamma", target="gamma-local")
    identity = {
        "workload": "content-release",
        "compose_project": "quwoquan_gamma_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=receipt_path,
    ):
        subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="prepared",
            **identity,
        )
        subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="partial",
            **identity,
        )
        receipt = subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="partial",
            failure="startup exited with status 1",
            cleanup_failure="compose down failed",
        )

    assert receipt["status"] == "partial"
    assert receipt["failure"] == "startup exited with status 1"
    assert receipt["cleanupFailure"] == "compose down failed"


def test_startup_attempt_rejects_cross_attempt_and_invalid_transition(
    tmp_path: Path,
) -> None:
    composition = _composition(environment="beta", target="beta-local")
    identity = {
        "workload": "content-release",
        "compose_project": "quwoquan_beta_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=tmp_path / "startup_attempt.json",
    ):
        subject.transition_startup_attempt(
            env="beta",
            target="beta-local",
            attempt_id="attempt-1",
            status="prepared",
            **identity,
        )
        with pytest.raises(ValueError, match="identity mismatch"):
            subject.transition_startup_attempt(
                env="beta",
                target="beta-local",
                attempt_id="attempt-2",
                status="partial",
                compose_project="quwoquan_beta_release",
                configuration_digest="sha256:" + "c" * 64,
                image_transport_tag="sha256:" + "a" * 64,
                image_composition=composition,
            )
        with pytest.raises(ValueError, match="transition is invalid"):
            subject.transition_startup_attempt(
                env="beta",
                target="beta-local",
                attempt_id="attempt-1",
                status="running",
            )


def test_workload_receipts_remain_isolated(tmp_path: Path) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    composition = _composition()
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "compose_project": "quwoquan_alpha",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "observability_log_sink_digest": "sha256:" + "e" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=receipt_path,
    ):
        for workload, attempt_id in (
            ("content-release", "content-1"),
            ("full", "full-1"),
        ):
            subject.transition_startup_attempt(
                attempt_id=attempt_id,
                status="prepared",
                workload=workload,
                **common,
            )
            subject.transition_startup_attempt(
                attempt_id=attempt_id,
                status="partial",
                workload=workload,
                **common,
            )
            subject.transition_startup_attempt(
                attempt_id=attempt_id,
                status="running",
                workload=workload,
                **common,
            )
            subject.transition_startup_attempt(
                attempt_id=attempt_id,
                status="stopped",
                workload=workload,
                **common,
            )

        content = subject.load_workload_startup_attempt(
            "alpha-local",
            "content-release",
        )
        full = subject.load_workload_startup_attempt("alpha-local", "full")

    assert content is not None and content["attemptId"] == "content-1"
    assert full is not None and full["attemptId"] == "full-1"


def test_startup_attempt_rejects_unbound_candidate_and_incomplete_images(
    tmp_path: Path,
) -> None:
    composition = _composition()
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "attempt_id": "attempt-1",
        "status": "prepared",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha",
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=tmp_path / "startup_attempt.json",
    ):
        with pytest.raises(ValueError, match="candidate digest"):
            subject.transition_startup_attempt(candidate_digest="", **common)

        incomplete = {**composition, "images": {}, "ociImages": {}}
        with pytest.raises(ValueError, match="has no images"):
            subject.transition_startup_attempt(
                candidate_digest="sha256:" + "b" * 64,
                image_composition=incomplete,
                **{key: value for key, value in common.items() if key != "image_composition"},
            )


def test_startup_attempt_loader_rejects_legacy_schema_only_receipt(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    receipt_path.write_text(
        json.dumps({"schema": subject.SCHEMA, "status": "stopped"}),
        encoding="utf-8",
    )
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=receipt_path,
    ), pytest.raises(ValueError, match="fields mismatch"):
        subject.load_startup_attempt("alpha-local")


def test_startup_composition_uses_the_complete_explicit_candidate_oci() -> None:
    manifest = _oci_manifest()
    composition = subject.image_composition_from_candidate_oci(
        manifest,
        expected_environment="alpha",
        expected_target="alpha-local",
    )

    assert set(composition["images"]) == {
        "api-edge",
        "provider-protocol-substitute",
        "sms-provider-substitute",
    }
    assert composition["images"]["sms-provider-substitute"] == {
        "ref": "sha256:" + "5" * 64
    }
    assert composition["configurationDigest"] == manifest["configurationDigest"]
    assert composition["buildInputDigest"] == manifest["buildInputDigest"]
    assert composition["imageDigest"] == manifest["imageDigest"]
    assert composition["ociImages"] == manifest["images"]

    tampered = dict(manifest)
    tampered["imageDigest"] = "sha256:" + "9" * 64
    with pytest.raises(ValueError, match="imageDigest mismatch"):
        subject.image_composition_from_candidate_oci(tampered)


def test_new_attempt_never_inherits_stopped_attempt_identity(tmp_path: Path) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    composition = _composition(environment="gamma", target="gamma-local")
    identity = {
        "env": "gamma",
        "target": "gamma-local",
        "workload": "full",
        "compose_project": "quwoquan_gamma_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "observability_log_sink_digest": "sha256:" + "e" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
        "run_root": str(tmp_path / "env/gamma/runs/run-1"),
    }
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        subject.transition_startup_attempt(
            attempt_id="attempt-1", status="prepared", **identity
        )
        subject.transition_startup_attempt(
            attempt_id="attempt-1", status="stopped", **identity
        )
        with pytest.raises(ValueError, match="requires workload"):
            subject.transition_startup_attempt(
                env="gamma",
                target="gamma-local",
                attempt_id="attempt-2",
                status="prepared",
            )
        with pytest.raises(ValueError, match="new attemptId"):
            subject.transition_startup_attempt(
                attempt_id="attempt-1", status="prepared", **identity
            )


def test_existing_attempt_rejects_every_identity_mutation(tmp_path: Path) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    composition = _composition(environment="gamma", target="gamma-local")
    identity = {
        "env": "gamma",
        "target": "gamma-local",
        "workload": "full",
        "compose_project": "quwoquan_gamma_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "observability_log_sink_digest": "sha256:" + "e" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
        "run_root": str(tmp_path / "env/gamma/runs/run-1"),
    }
    mutations: tuple[tuple[str, object], ...] = (
        ("workload", "content-release"),
        ("compose_project", "quwoquan_gamma_other"),
        ("candidate_digest", "sha256:" + "1" * 64),
        ("configuration_digest", "sha256:" + "2" * 64),
        ("provider_runtime_digest", "sha256:" + "3" * 64),
        ("observability_log_sink_digest", "sha256:" + "4" * 64),
        ("image_transport_tag", "sha256:" + "5" * 64),
        (
            "image_composition",
            {
                "imageVersion": "sha256:" + "6" * 64,
                "images": {"api-edge": {"ref": "sha256:" + "7" * 64}},
            },
        ),
        ("run_root", str(tmp_path / "env/gamma/runs/run-2")),
    )
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        subject.transition_startup_attempt(
            attempt_id="attempt-1", status="prepared", **identity
        )
        for field, value in mutations:
            with pytest.raises(ValueError, match="identity mismatch"):
                subject.transition_startup_attempt(
                    env="gamma",
                    target="gamma-local",
                    attempt_id="attempt-1",
                    status="partial",
                    **{field: value},
                )

        partial = subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="partial",
            failure="startup failed",
            cleanup_failure="cleanup failed",
        )

    for field, value in identity.items():
        payload_field = {
            "compose_project": "composeProject",
            "candidate_digest": "candidateDigest",
            "configuration_digest": "configurationDigest",
            "provider_runtime_digest": "providerRuntimeDigest",
            "observability_log_sink_digest": "observabilityLogSinkDigest",
            "image_transport_tag": "imageTransportTag",
            "image_composition": "imageComposition",
            "run_root": "runRoot",
        }.get(field, field)
        assert partial[payload_field] == value
    assert partial["failure"] == "startup failed"
    assert partial["cleanupFailure"] == "cleanup failed"


def test_startup_attempt_rejects_run_root_outside_environment_evidence(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    outside = tmp_path / "outside-run"
    composition = _composition()
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
        pytest.raises(ValueError, match="target-environment run evidence"),
    ):
        subject.transition_startup_attempt(
            env="alpha",
            target="alpha-local",
            attempt_id="attempt-1",
            status="prepared",
            workload="content-release",
            compose_project="quwoquan_alpha_release",
            candidate_digest="sha256:" + "b" * 64,
            configuration_digest="sha256:" + "c" * 64,
            provider_runtime_digest="sha256:" + "d" * 64,
            image_transport_tag=str(composition["imageVersion"]),
            image_composition=composition,
            run_root=str(outside),
        )

    assert not receipt_path.exists()
    assert not (outside / "startup_attempt.json").exists()


def test_startup_attempt_rejects_symlinked_parent_and_final_path(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    process_root = tmp_path / "process-root"
    process_root.mkdir()
    symlinked_parent = process_root / "process"
    symlinked_parent.symlink_to(outside, target_is_directory=True)
    composition = _composition()
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "attempt_id": "attempt-1",
        "status": "prepared",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": str(composition["imageVersion"]),
        "image_composition": composition,
    }
    with (
        mock.patch.object(
            subject,
            "startup_attempt_path",
            return_value=symlinked_parent / "startup_attempt.json",
        ),
        pytest.raises(ValueError, match="symlink or non-directory"),
    ):
        subject.transition_startup_attempt(**common)
    assert not (outside / "startup_attempt.json").exists()

    real_parent = tmp_path / "real-process"
    real_parent.mkdir()
    external_file = outside / "external.json"
    external_file.write_text("unchanged", encoding="utf-8")
    final_path = real_parent / "startup_attempt.json"
    final_path.symlink_to(external_file)
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=final_path),
        pytest.raises(ValueError, match="symlink or non-regular file"),
    ):
        subject.transition_startup_attempt(**common)
    assert external_file.read_text(encoding="utf-8") == "unchanged"


def test_prepared_cli_requires_explicit_candidate_oci_file(tmp_path: Path) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path
    )
    composition = _composition()
    argv = [
        "startup_attempt_receipt.py",
        "--env",
        "alpha",
        "--target",
        "alpha-local",
        "--attempt-id",
        "attempt-1",
        "--status",
        "prepared",
        "--workload",
        "content-release",
        "--compose-project",
        "quwoquan_alpha_release",
        "--candidate-digest",
        "sha256:" + "b" * 64,
        "--configuration-digest",
        "sha256:" + "c" * 64,
        "--provider-runtime-digest",
        "sha256:" + "d" * 64,
        "--image-transport-tag",
        str(composition["imageVersion"]),
    ]
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        pytest.raises(ValueError, match="requires image composition"),
    ):
        subject.main()

    with (
        mock.patch.object(
            sys,
            "argv",
            [*argv, "--image-composition-file", str(oci_path)],
        ),
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(
            subject,
            "active_candidate_manifest_path",
            return_value=active_path,
        ),
        mock.patch.object(
            subject,
            "deployment_candidate_dir",
            return_value=candidate_root,
        ),
        mock.patch.object(
            subject,
            "load_candidate_manifest",
            return_value=candidate,
        ),
    ):
        assert subject.main() == 0

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["imageComposition"] == composition


def test_candidate_oci_loader_requires_exact_active_descriptor_path(
    tmp_path: Path,
) -> None:
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path
    )
    arbitrary_path = tmp_path / "copied-oci-images.json"
    arbitrary_path.write_text(oci_path.read_text(encoding="utf-8"), encoding="utf-8")
    patches = (
        mock.patch.object(
            subject,
            "active_candidate_manifest_path",
            return_value=active_path,
        ),
        mock.patch.object(
            subject,
            "deployment_candidate_dir",
            return_value=candidate_root,
        ),
        mock.patch.object(
            subject,
            "load_candidate_manifest",
            return_value=candidate,
        ),
    )
    with patches[0], patches[1], patches[2]:
        loaded = subject.load_candidate_oci_image_composition(
            oci_path,
            expected_environment="alpha",
            expected_target="alpha-local",
            expected_candidate_digest="sha256:" + "b" * 64,
        )
        assert loaded == _composition()
        with pytest.raises(ValueError, match="active candidate fixed artifact"):
            subject.load_candidate_oci_image_composition(
                arbitrary_path,
                expected_environment="alpha",
                expected_target="alpha-local",
            )


def test_candidate_oci_loader_rejects_symlinked_active_artifacts(
    tmp_path: Path,
) -> None:
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path
    )
    outside = tmp_path / "outside-oci-images.json"
    outside.write_text(oci_path.read_text(encoding="utf-8"), encoding="utf-8")
    oci_path.unlink()
    oci_path.symlink_to(outside)
    with (
        mock.patch.object(
            subject,
            "active_candidate_manifest_path",
            return_value=active_path,
        ),
        mock.patch.object(
            subject,
            "deployment_candidate_dir",
            return_value=candidate_root,
        ),
        mock.patch.object(
            subject,
            "load_candidate_manifest",
            return_value=candidate,
        ),
        pytest.raises(ValueError, match="symlink or non-regular file"),
    ):
        subject.load_candidate_oci_image_composition(
            oci_path,
            expected_environment="alpha",
            expected_target="alpha-local",
        )


def test_candidate_oci_loader_cross_checks_active_candidate_digests(
    tmp_path: Path,
) -> None:
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path
    )
    mismatches = (
        ("runtimeConfigDigest", "configurationDigest"),
        ("buildInputDigest", "buildInputDigest"),
        ("imageDigest", "imageDigest"),
    )
    for candidate_field, _ in mismatches:
        tampered_candidate = {
            **candidate,
            candidate_field: "sha256:" + "9" * 64,
        }
        with (
            mock.patch.object(
                subject,
                "active_candidate_manifest_path",
                return_value=active_path,
            ),
            mock.patch.object(
                subject,
                "deployment_candidate_dir",
                return_value=candidate_root,
            ),
            mock.patch.object(
                subject,
                "load_candidate_manifest",
                return_value=tampered_candidate,
            ),
            pytest.raises(ValueError, match="differs from active candidate"),
        ):
            subject.load_candidate_oci_image_composition(
                oci_path,
                expected_environment="alpha",
                expected_target="alpha-local",
            )


def test_candidate_oci_loader_rejects_active_pointer_change(
    tmp_path: Path,
) -> None:
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path
    )
    original_secure_read = subject._secure_read
    pointer_reads = 0

    def _changing_pointer(path: Path, *, label: str = "") -> bytes | None:
        nonlocal pointer_reads
        payload = original_secure_read(path, label=label)
        if path == active_path:
            pointer_reads += 1
            if pointer_reads == 2:
                assert payload is not None
                changed = json.loads(payload.decode("utf-8"))
                changed["baselineId"] = "sha256:" + "8" * 64
                return json.dumps(changed).encode("utf-8")
        return payload

    with (
        mock.patch.object(
            subject,
            "active_candidate_manifest_path",
            return_value=active_path,
        ),
        mock.patch.object(
            subject,
            "deployment_candidate_dir",
            return_value=candidate_root,
        ),
        mock.patch.object(
            subject,
            "load_candidate_manifest",
            return_value=candidate,
        ),
        mock.patch.object(subject, "_secure_read", side_effect=_changing_pointer),
        pytest.raises(ValueError, match="changed during OCI validation"),
    ):
        subject.load_candidate_oci_image_composition(
            oci_path,
            expected_environment="alpha",
            expected_target="alpha-local",
        )


def test_receipt_cross_checks_top_level_configuration_and_full_oci_closure(
    tmp_path: Path,
) -> None:
    composition = _composition()
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "attempt_id": "attempt-1",
        "status": "prepared",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=tmp_path / "startup_attempt.json",
    ):
        with pytest.raises(ValueError, match="configuration differs"):
            subject.transition_startup_attempt(
                **{
                    **common,
                    "configuration_digest": "sha256:" + "9" * 64,
                }
            )

        tampered = json.loads(json.dumps(composition))
        tampered["ociImages"]["api-edge"]["ref"] = "tampered/source:tag"
        with pytest.raises(ValueError, match="OCI imageDigest mismatch"):
            subject.transition_startup_attempt(
                **{**common, "image_composition": tampered}
            )


def test_fanout_failure_rolls_back_every_replica_at_each_commit_point(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    composition = _composition(environment="gamma", target="gamma-local")
    identity = {
        "env": "gamma",
        "target": "gamma-local",
        "workload": "full",
        "compose_project": "quwoquan_gamma_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "observability_log_sink_digest": "sha256:" + "e" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
    }
    run_one = tmp_path / "env/gamma/runs/run-1"
    run_two = tmp_path / "env/gamma/runs/run-2"
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        subject.transition_startup_attempt(
            attempt_id="attempt-1",
            status="prepared",
            run_root=str(run_one),
            **identity,
        )
        subject.transition_startup_attempt(
            attempt_id="attempt-1",
            status="stopped",
            run_root=str(run_one),
            **identity,
        )
        workload_path = (
            receipt_path.parent / "workloads/full/startup_attempt.json"
        )
        run_two_path = run_two / "startup_attempt.json"
        before_canonical = receipt_path.read_bytes()
        before_workload = workload_path.read_bytes()
        original_commit = subject._commit_staged_receipt

        for failure_path in (workload_path, run_two_path, receipt_path):
            failed = False

            def _commit_then_fail(
                staged: subject._StagedReceiptWrite,
            ) -> None:
                nonlocal failed
                original_commit(staged)
                if staged.path == failure_path and not failed:
                    failed = True
                    raise OSError(f"injected commit failure: {failure_path}")

            with (
                mock.patch.object(
                    subject,
                    "_commit_staged_receipt",
                    side_effect=_commit_then_fail,
                ),
                pytest.raises(OSError, match="injected commit failure"),
            ):
                subject.transition_startup_attempt(
                    attempt_id="attempt-2",
                    status="prepared",
                    run_root=str(run_two),
                    **identity,
                )

            assert receipt_path.read_bytes() == before_canonical
            assert workload_path.read_bytes() == before_workload
            assert not run_two_path.exists()
            assert not subject._fanout_transaction_path(receipt_path).exists()

    assert json.loads(receipt_path.read_text(encoding="utf-8"))["attemptId"] == (
        "attempt-1"
    )


def test_loader_recovers_a_crash_journal_before_exposing_any_replica(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    run_root = tmp_path / "env/alpha/runs/run-1"
    workload_path = (
        receipt_path.parent / "workloads/content-release/startup_attempt.json"
    )
    run_path = run_root / "startup_attempt.json"
    composition = _composition()
    original_commit = subject._commit_staged_receipt
    committed_workload = False

    def _commit_then_crash(staged: subject._StagedReceiptWrite) -> None:
        nonlocal committed_workload
        original_commit(staged)
        if staged.path == workload_path and not committed_workload:
            committed_workload = True
            raise OSError("simulated process interruption")

    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
        mock.patch.object(
            subject,
            "_commit_staged_receipt",
            side_effect=_commit_then_crash,
        ),
        mock.patch.object(
            subject,
            "_rollback_fanout_transaction",
            side_effect=OSError("simulated rollback interruption"),
        ),
        pytest.raises(RuntimeError, match="rollback was incomplete"),
    ):
        subject.transition_startup_attempt(
            env="alpha",
            target="alpha-local",
            attempt_id="attempt-1",
            status="prepared",
            workload="content-release",
            compose_project="quwoquan_alpha_release",
            candidate_digest="sha256:" + "b" * 64,
            configuration_digest="sha256:" + "c" * 64,
            provider_runtime_digest="sha256:" + "d" * 64,
            image_transport_tag=str(composition["imageVersion"]),
            image_composition=composition,
            run_root=str(run_root),
        )

    assert workload_path.exists()
    assert subject._fanout_transaction_path(receipt_path).exists()
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        assert subject.load_startup_attempt("alpha-local") is None

    assert not workload_path.exists()
    assert not run_path.exists()
    assert not receipt_path.exists()
    assert not subject._fanout_transaction_path(receipt_path).exists()


def test_fanout_never_follows_or_replaces_an_unsafe_transaction_journal(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    receipt_path.parent.mkdir(parents=True)
    external = tmp_path / "external-journal.json"
    external.write_text("external remains unchanged\n", encoding="utf-8")
    journal_path = subject._fanout_transaction_path(receipt_path)
    journal_path.symlink_to(external)
    composition = _composition()

    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
        pytest.raises(ValueError, match="symlink or non-regular file"),
    ):
        subject.transition_startup_attempt(
            env="alpha",
            target="alpha-local",
            attempt_id="attempt-1",
            status="prepared",
            workload="content-release",
            compose_project="quwoquan_alpha_release",
            candidate_digest="sha256:" + "b" * 64,
            configuration_digest="sha256:" + "c" * 64,
            provider_runtime_digest="sha256:" + "d" * 64,
            image_transport_tag=str(composition["imageVersion"]),
            image_composition=composition,
        )

    assert journal_path.is_symlink()
    assert external.read_text(encoding="utf-8") == "external remains unchanged\n"
    assert not receipt_path.exists()


def test_fanout_prevalidates_every_destination_before_any_write(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    run_root = tmp_path / "env/alpha/runs/run-1"
    composition = _composition()
    workload_path = receipt_path.parent / "workloads/content-release/startup_attempt.json"
    original_prevalidate = subject._prevalidate_write_path

    def _fail_run_prevalidation(path: Path) -> None:
        if path == run_root / "startup_attempt.json":
            raise OSError("injected prevalidation failure")
        original_prevalidate(path)

    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
        mock.patch.object(
            subject,
            "_prevalidate_write_path",
            side_effect=_fail_run_prevalidation,
        ),
        pytest.raises(OSError, match="injected prevalidation failure"),
    ):
        subject.transition_startup_attempt(
            env="alpha",
            target="alpha-local",
            attempt_id="attempt-1",
            status="prepared",
            workload="content-release",
            compose_project="quwoquan_alpha_release",
            candidate_digest="sha256:" + "b" * 64,
            configuration_digest="sha256:" + "c" * 64,
            provider_runtime_digest="sha256:" + "d" * 64,
            image_transport_tag=str(composition["imageVersion"]),
            image_composition=composition,
            run_root=str(run_root),
        )

    assert not workload_path.exists()
    assert not receipt_path.exists()


def test_run_root_rejects_a_different_existing_attempt_before_fanout(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    run_root = tmp_path / "env/alpha/runs/shared-run"
    composition = _composition()
    identity = {
        "env": "alpha",
        "target": "alpha-local",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha_release",
        "candidate_digest": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "provider_runtime_digest": "sha256:" + "d" * 64,
        "image_transport_tag": composition["imageVersion"],
        "image_composition": composition,
        "run_root": str(run_root),
    }
    with (
        mock.patch.object(subject, "startup_attempt_path", return_value=receipt_path),
        mock.patch.object(subject, "output_root", return_value=tmp_path),
    ):
        subject.transition_startup_attempt(
            attempt_id="attempt-1", status="prepared", **identity
        )
        subject.transition_startup_attempt(
            attempt_id="attempt-1", status="stopped", **identity
        )
        before = receipt_path.read_bytes()
        with pytest.raises(ValueError, match="different attempt"):
            subject.transition_startup_attempt(
                attempt_id="attempt-2", status="prepared", **identity
            )

    assert receipt_path.read_bytes() == before

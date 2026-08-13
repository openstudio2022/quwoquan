"""startup attempt receipt：启动尝试事务生命周期、身份守恒与 run root 边界契约。

由 1000 行硬顶拆分自根目录 test_startup_attempt_receipt__local_contract_test.py；
测试逐字搬移，共享构造 helper 见
quwoquan_ops/tests/support/startup_attempt_receipt_test_support.py。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import startup_attempt_receipt as subject
from quwoquan_ops.tests.support.startup_attempt_receipt_test_support import (
    _composition,
    _oci_manifest,
)


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

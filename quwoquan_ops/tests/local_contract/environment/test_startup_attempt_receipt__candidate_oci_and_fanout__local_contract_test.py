"""startup attempt receipt：candidate OCI 装载校验与 receipt replica fanout 事务契约。

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
    _active_candidate_files,
    _composition,
)


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
        ("configurationDigest", "configurationDigest"),
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

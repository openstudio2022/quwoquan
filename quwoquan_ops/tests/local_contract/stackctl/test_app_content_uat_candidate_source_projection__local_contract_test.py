"""App UAT builds only from the active candidate's exact input capsule."""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch
from quwoquan_ops.cli.commands.app_preflight_uat import (
    _app_content_canonical_launch_command,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _launcher_environment(root: Path) -> dict[str, str]:
    """设备 inventory/SDK 是外部边界；解析和参数校验仍使用生产实现。"""
    binary_root = root / "bin"
    binary_root.mkdir()
    flutter = binary_root / "flutter"
    pinned_version = (_REPO_ROOT / "quwoquan_app/.flutter-version").read_text().strip()
    flutter.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"capture = pathlib.Path({str(root / 'flutter-argv.jsonl')!r})\n"
        "with capture.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:] == ['devices', '--machine']:\n"
        "    print(json.dumps([{'id': 'emulator-5554', "
        "'targetPlatform': 'android-arm64', 'emulator': True}]))\n"
        "elif sys.argv[1:] == ['--version', '--machine']:\n"
        f"    print(json.dumps({{'frameworkVersion': {pinned_version!r}}}))\n"
        "else:\n"
        "    raise SystemExit('unexpected Flutter operation: ' + repr(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    flutter.chmod(0o755)
    return {
        "HOME": str(root),
        "PATH": os.pathsep.join(
            (str(binary_root), str(Path(sys.executable).parent), os.environ["PATH"])
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_REAL_FLUTTER": str(flutter),
    }


def _fixture(
    root: Path,
    *,
    canonical_launcher: bool = False,
) -> tuple[dict[str, object], dict[str, object], Path]:
    capsule = root / "candidate/input-capsule"
    files = {
        "quwoquan_app/run.sh": b"#!/bin/sh\necho candidate-app\n",
        "quwoquan_ops/cli/stackctl.py": b"CANDIDATE_OPS = True\n",
        "quwoquan_app/lib/main_prod.dart": b"// candidate bytes\n",
    }
    if canonical_launcher:
        # control、source policy、IDE handoff 与 topology 必须执行真实源代码，
        # 连同 import/metadata 闭包封入 capsule；不以 helper 替身放行前置校验。
        for relative in (
            "quwoquan_app/run.sh",
            "quwoquan_app/.flutter-version",
            "quwoquan_app/scripts/device/build_launcher_handoff.py",
            "quwoquan_app/scripts/device/canonical_app_instance/__init__.py",
            "quwoquan_app/scripts/device/canonical_app_instance/arguments.py",
            "quwoquan_app/scripts/device/canonical_app_instance/vm_service_info_file.py",
            "quwoquan_app/scripts/tools/flutter_facade/flutter_facade.py",
            "quwoquan_app/scripts/tools/flutter_facade/resolve_real_flutter.py",
            "quwoquan_ops/cli/lib/app_debug_preflight_handoff.py",
            "quwoquan_ops/cli/lib/app_identity.py",
            "quwoquan_ops/cli/lib/app_launch_manifest_contract.py",
            "quwoquan_ops/cli/lib/app_launch_manifest_schema.py",
            "quwoquan_ops/cli/lib/app_runtime_config_signing.py",
            "quwoquan_ops/cli/lib/common.py",
            "quwoquan_ops/cli/lib/data_plane_binding.py",
            "quwoquan_ops/cli/lib/dev_up.py",
            "quwoquan_ops/cli/lib/environment_topology.py",
            "quwoquan_ops/cli/lib/generated/app_launch_contract.py",
            "quwoquan_ops/cli/lib/local_app_runtime_config_keys.py",
            "quwoquan_ops/cli/lib/local_runtime_consumer_lease.py",
            "quwoquan_ops/cli/lib/openssl3_resolver.py",
            "quwoquan_ops/cli/lib/output_paths.py",
            "quwoquan_ops/cli/lib/port_manifest.py",
            "quwoquan_ops/cli/lib/service_core_composition.py",
            "quwoquan_ops/environments/domain_governance.yaml",
            "quwoquan_ops/environments/local_env_port_manifest.yaml",
            "quwoquan_ops/environments/alpha/runtime.yaml",
            "quwoquan_ops/environments/beta/runtime.yaml",
            "quwoquan_ops/environments/gamma/runtime.yaml",
            "quwoquan_ops/environments/prod/runtime.yaml",
            "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml",
            "quwoquan_service/services/content-service/environments/beta/deploy/kustomization.yaml",
        ):
            files[relative] = (_REPO_ROOT / relative).read_bytes()
        # 只替换服务 readiness 的外部命令；意外触及租约、信任或其他操作即失败。
        files["quwoquan_ops/cli/stackctl.py"] = (
            b"import json, sys\n"
            b"assert sys.argv[1:] == ['--output-format', 'json', "
            b"'app-debug-preflight', '--purpose', 'content_live', "
            b"'--target', 'beta-local', '--runtime-mode', 'test_live'], sys.argv\n"
            b"print(json.dumps({'purpose': 'content_live', 'status': 'passed', "
            b"'nonPromotable': True, 'warnings': []}))\n"
        )
    entries: list[dict[str, object]] = []
    for relative, content in files.items():
        path = capsule / "repo" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        mode = 0o555 if relative.endswith(".sh") else 0o444
        path.chmod(mode)
        entries.append(
            {
                "logicalPath": relative,
                "capsulePath": f"repo/{relative}",
                "kind": "file",
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "mode": mode,
            }
        )
    manifest_path = capsule / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    manifest = {
        "schema": "stackctl-package-input-capsule.v1",
        "baselineId": _digest("a"),
        "sourceRevision": "b" * 40,
        "workspaceStatusDigest": _digest("c"),
        "deploymentInputDigest": _digest("d"),
        "deploymentInputFileCount": len(entries),
        "deploymentInputRoots": [
            "quwoquan_app",
            "quwoquan_ops/cli",
            "quwoquan_ops/environments",
        ],
        "entries": entries,
    }
    runtime_binding: dict[str, object] = {
        "environment": "beta",
        "target": "beta-local",
        "candidateDigest": manifest["baselineId"],
        "packageDigest": _digest("e"),
        "sourceRevision": manifest["sourceRevision"],
        "sourceCapsuleWorkspaceStatusDigest": manifest["workspaceStatusDigest"],
        "sourceCapsuleDigest": manifest["deploymentInputDigest"],
        "sourceCapsuleManifestRef": str(manifest_path),
    }
    return manifest, runtime_binding, manifest_path


def test_projection_uses_candidate_bytes_without_synthetic_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = tmp_path / "output"
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "source-projection",
        evidence_path=output_root / "source-projection.json",
    )

    projected_root = Path(projection["sourceProjectionRoot"])
    assert (projected_root / "quwoquan_app/lib/main_prod.dart").read_bytes() == (
        b"// candidate bytes\n"
    )
    assert not (projected_root / ".git").exists()
    assert (
        stat.S_IMODE((projected_root / "quwoquan_app/run.sh").stat().st_mode) == 0o755
    )
    assert (
        stat.S_IMODE(
            (projected_root / "quwoquan_app/lib/main_prod.dart").stat().st_mode
        )
        == 0o644
    )
    evidence = json.loads(
        Path(projection["sourceProjectionEvidenceRef"]).read_text(encoding="utf-8")
    )
    assert evidence["candidateDigest"] == runtime_binding["candidateDigest"]
    assert evidence["packageDigest"] == runtime_binding["packageDigest"]
    assert evidence["sourceProjectionDigest"] == projection["sourceProjectionDigest"]
    assert evidence["sourceProjectionFileCount"] == len(manifest["entries"])


def test_projection_post_copy_cas_rejects_copy_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    original_copy = launch._copy_projection_regular_file

    def corrupt_copy(**kwargs: object) -> None:
        original_copy(**kwargs)
        destination = Path(str(kwargs["destination"]))
        if destination.name == "main_prod.dart":
            destination.write_bytes(b"corrupted after copy\n")

    monkeypatch.setattr(launch, "_copy_projection_regular_file", corrupt_copy)
    output_root = tmp_path / "output"
    with pytest.raises(ValueError, match="entry CAS mismatch"):
        launch.materialize_app_content_launch_projection(
            runtime_binding=runtime_binding,
            output_root=output_root,
            projection_root=output_root / "source-projection",
            evidence_path=output_root / "source-projection.json",
        )


def test_projection_boundary_rejects_post_copy_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = tmp_path / "output"
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "source-projection",
        evidence_path=output_root / "source-projection.json",
    )
    projected_source = (
        Path(projection["sourceProjectionRoot"]) / "quwoquan_app/lib/main_prod.dart"
    )
    projected_source.write_bytes(b"drifted before build\n")

    with pytest.raises(ValueError, match="entry CAS mismatch"):
        launch.verify_app_content_launch_projection(
            projection_root=Path(projection["sourceProjectionRoot"]),
            evidence_path=Path(projection["sourceProjectionEvidenceRef"]),
            reject_unmanifested=True,
        )


def test_projection_boundary_rejects_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, manifest_path = _fixture(tmp_path)
    link_relative = "quwoquan_app/lib/main_prod_link.dart"
    capsule_link = manifest_path.parent / "repo" / link_relative
    capsule_link.symlink_to("main_prod.dart")
    link_target = os.readlink(capsule_link).encode("utf-8")
    manifest["entries"].append(
        {
            "logicalPath": link_relative,
            "capsulePath": f"repo/{link_relative}",
            "kind": "symlink",
            "digest": "sha256:" + hashlib.sha256(link_target).hexdigest(),
            "size": len(link_target),
            "mode": 0,
        }
    )
    manifest["deploymentInputFileCount"] = len(manifest["entries"])
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = tmp_path / "output"
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "source-projection",
        evidence_path=output_root / "source-projection.json",
    )
    projected_link = Path(projection["sourceProjectionRoot"]) / link_relative
    projected_link.unlink()
    outside = tmp_path / "outside.dart"
    outside.write_text("outside\n", encoding="utf-8")
    projected_link.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink escapes build root"):
        launch.verify_app_content_launch_projection(
            projection_root=Path(projection["sourceProjectionRoot"]),
            evidence_path=Path(projection["sourceProjectionEvidenceRef"]),
            reject_unmanifested=False,
        )


def test_projection_rejects_candidate_or_capsule_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    runtime_binding["candidateDigest"] = _digest("f")
    with pytest.raises(ValueError, match="candidate/source capsule identity drifted"):
        launch.materialize_app_content_launch_projection(
            runtime_binding=runtime_binding,
            output_root=tmp_path / "output",
            projection_root=tmp_path / "output/source-projection",
            evidence_path=tmp_path / "output/source-projection.json",
        )


def test_projection_rejects_incomplete_launch_input_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    manifest["deploymentInputRoots"] = ["quwoquan_app"]
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    with pytest.raises(ValueError, match="lacks canonical launch closure"):
        launch.materialize_app_content_launch_projection(
            runtime_binding=runtime_binding,
            output_root=tmp_path / "output",
            projection_root=tmp_path / "output/source-projection",
            evidence_path=tmp_path / "output/source-projection.json",
        )


def test_private_launch_control_binds_candidate_package_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(tmp_path)
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = tmp_path / "output"
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "source-projection",
        evidence_path=output_root / "source-projection.json",
    )
    control = launch.write_app_content_launch_control(
        runtime_binding=runtime_binding,
        projection=projection,
        output_root=output_root,
        control_path=output_root / "attempt/control.json",
        attempt_path=output_root / "attempt/attempt.json",
        report_path=output_root / "attempt/report.json",
        terminal_receipt_path=output_root / "attempt/startup-terminal.json",
        platform="android",
        device_id="emulator-5554",
        build_projection_policy_id=(launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID),
        build_projection_seal_path=(output_root / "attempt/build-projection-seal.json"),
        expected_build_projection_digest=None,
    )

    assert control["candidateDigest"] == runtime_binding["candidateDigest"]
    assert control["packageDigest"] == runtime_binding["packageDigest"]
    assert control["sourceProjectionRoot"] == projection["sourceProjectionRoot"]
    assert control["buildProjectionPolicyId"] == (
        launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID
    )
    assert control["expectedBuildProjectionDigest"] is None
    assert not Path(control["buildProjectionSealRef"]).exists()
    assert stat.S_IMODE(Path(control["controlRef"]).stat().st_mode) == 0o600


def test_projected_run_sh_uses_canonical_output_root_for_private_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, _manifest_path = _fixture(
        tmp_path,
        canonical_launcher=True,
    )
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = (tmp_path / "canonical-output").resolve()
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "uat/source-projection",
        evidence_path=output_root / "uat/source-projection.json",
    )
    attempt_path = output_root / "uat/attempt/attempt.json"
    report_path = attempt_path.with_name("report.json")
    control = launch.write_app_content_launch_control(
        runtime_binding=runtime_binding,
        projection=projection,
        output_root=output_root,
        control_path=attempt_path.with_name("control.json"),
        attempt_path=attempt_path,
        report_path=report_path,
        terminal_receipt_path=attempt_path.with_name("startup-terminal.json"),
        platform="android",
        device_id="emulator-5554",
        build_projection_policy_id=(launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID),
        build_projection_seal_path=(
            attempt_path.with_name("build-projection-seal.json")
        ),
        expected_build_projection_digest=None,
    )
    projected_app = Path(projection["sourceProjectionRoot"]) / "quwoquan_app"
    command, child_environment = _app_content_canonical_launch_command(
        environment="beta",
        target="beta-local",
        device_id="emulator-5554",
        attempt_path=attempt_path,
        report_path=report_path,
        output_root=output_root,
        app_root=projected_app,
        launch_control=control,
    )
    base_environment = {
        **_launcher_environment(tmp_path),
        **child_environment,
        # control 通过后明确停在 SDK 外部边界，不依赖 sandbox 漏文件报错。
        "QWQ_REAL_FLUTTER": str(tmp_path / "unavailable-sdk/bin/flutter"),
    }
    legacy_environment = dict(base_environment)
    legacy_environment.pop("QWQ_OUTPUT_ROOT")
    legacy = subprocess.run(
        command,
        cwd=projected_app,
        env=legacy_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert legacy.returncode == 2
    assert "canonical launch control escapes QWQ_OUTPUT_ROOT" in legacy.stderr

    crossed = subprocess.run(
        command,
        cwd=projected_app,
        env=base_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert crossed.returncode == 2
    assert "canonical launch control escapes QWQ_OUTPUT_ROOT" not in crossed.stderr
    assert "GATE_BLOCK: unable to resolve the pinned Flutter SDK identity" in (
        crossed.stderr
    )
    assert child_environment["QWQ_OUTPUT_ROOT"] == str(output_root)


def test_real_run_sh_remote_transport_failure_blocks_before_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, manifest_path = _fixture(
        tmp_path,
        canonical_launcher=True,
    )
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = (tmp_path / "canonical-output").resolve()
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "transport/source-projection",
        evidence_path=output_root / "transport/source-projection.json",
    )
    projected_app = Path(projection["sourceProjectionRoot"]) / "quwoquan_app"
    environment = _launcher_environment(tmp_path)
    adb_capture = tmp_path / "adb-argv.jsonl"
    adb = tmp_path / "bin/adb"
    adb.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"capture = pathlib.Path({str(adb_capture)!r})\n"
        "with capture.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "assert sys.argv[1:] == ['-s', 'emulator-5554', 'reverse', '--list']\n"
        "raise SystemExit(19)\n",
        encoding="utf-8",
    )
    adb.chmod(0o755)
    # 下游哨兵只记录是否跨过硬边界；绝不返回伪造 handoff 或构建证据。
    downstream_capture = tmp_path / "unexpected-downstream.txt"
    for script in ("supervise_app_launch.py", "prepare_flutter_dependencies.py"):
        (projected_app / "scripts/device" / script).write_text(
            "import pathlib\n"
            f"pathlib.Path({str(downstream_capture)!r}).write_text({script!r})\n"
            "raise SystemExit(97)\n",
            encoding="utf-8",
        )

    process = subprocess.run(
        [
            "bash", "run.sh", "--env", "beta", "--target", "beta-local",
            "--mode", "content-live", "-d", "emulator-5554",
        ],
        cwd=projected_app,
        env={
            **environment,
            "QWQ_OUTPUT_ROOT": str(output_root),
            "QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST": str(manifest_path),
            "QWQ_APP_LAUNCH_PROVENANCE": "canonical_launcher",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert process.returncode == 2, (process.stdout, process.stderr)
    assert "content delivery verification skipped" in process.stderr
    assert (
        "APP.LAUNCH.transport_unavailable: unable to read existing adb reverse mappings"
        in process.stderr
    ), (process.stdout, process.stderr)
    assert "GATE_BLOCK: failed to resolve device-specific Remote topology" in process.stderr
    assert "Traceback" not in process.stderr
    assert [json.loads(line) for line in adb_capture.read_text().splitlines()] == [
        ["-s", "emulator-5554", "reverse", "--list"]
    ]
    flutter_calls = [
        json.loads(line)
        for line in (tmp_path / "flutter-argv.jsonl").read_text().splitlines()
    ]
    assert ["--version", "--machine"] in flutter_calls
    assert not downstream_capture.exists()
    assert not list(output_root.rglob("startup-terminal.json"))
    # transport 在 attempt/evidence 路径分配前失败；不得借清理回执伪造已启动。
    assert not list(output_root.rglob("attempt.json"))
    assert not list(output_root.rglob("teardown.json"))


def test_real_run_sh_rejects_forged_workspace_ide_provenance_without_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, runtime_binding, manifest_path = _fixture(
        tmp_path,
        canonical_launcher=True,
    )
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = (tmp_path / "canonical-output").resolve()
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding=runtime_binding,
        output_root=output_root,
        projection_root=output_root / "forged-ide/source-projection",
        evidence_path=output_root / "forged-ide/source-projection.json",
    )
    projected_app = Path(projection["sourceProjectionRoot"]) / "quwoquan_app"
    supervisor_capture = tmp_path / "forged-ide-supervisor-capture.json"

    process = subprocess.run(
        (
            "bash",
            "run.sh",
            "--env",
            "beta",
            "--target",
            "beta-local",
            "--mode",
            "content-live",
            "-d",
            "emulator-5554",
            "--ide-vm-service-info",
            str(output_root / "forged-ide-vm-service.json"),
        ),
        cwd=projected_app,
        env={
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "PATH": os.environ["PATH"],
            "QWQ_OUTPUT_ROOT": str(output_root),
            "QWQ_TEST_SUPERVISOR_CAPTURE": str(supervisor_capture),
            "QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST": str(manifest_path),
            "QWQ_APP_LAUNCH_PROVENANCE": "workspace_ide_debug",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert process.returncode == 2
    assert "APP.LAUNCH.workspace_entrypoint_inactive" in process.stderr
    assert "not bound to the original workspace projection handoff" in process.stderr
    assert "workspace projection does not bind one original output runs root" in (
        process.stderr
    )
    assert "ModuleNotFoundError" not in process.stderr
    assert "No such file or directory" not in process.stderr
    assert not supervisor_capture.exists()

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
        files.update(
            {
                "quwoquan_app/run.sh": (
                    _REPO_ROOT / "quwoquan_app/run.sh"
                ).read_bytes(),
                "quwoquan_ops/cli/stackctl.py": (
                    b"import json\n"
                    b"print(json.dumps({"
                    b"'purpose': 'content_live', "
                    b"'status': 'passed', "
                    b"'nonPromotable': True, "
                    b"'warnings': []}))\n"
                ),
                "quwoquan_ops/cli/lib/__init__.py": b"",
                "quwoquan_ops/cli/lib/app_debug_preflight_handoff.py": (
                    b"def app_debug_preflight_purpose(run_mode):\n"
                    b"    return 'content_live' if run_mode == "
                    b"'content-live' else 'runtime'\n"
                ),
                "quwoquan_ops/cli/lib/dev_up.py": (
                    b"def find_device(*_args, **_kwargs):\n"
                    b"    return {'targetPlatform': 'android-arm64'}\n"
                ),
                ("quwoquan_app/scripts/device/canonical_app_instance/__init__.py"): b"",
                ("quwoquan_app/scripts/device/canonical_app_instance/arguments.py"): (
                    b"class CanonicalExecutorError(Exception):\n"
                    b"    pass\n\n"
                    b"def sanitize_attach_arguments(arguments):\n"
                    b"    return tuple(arguments)\n"
                ),
            }
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
        "environment": "alpha",
        "target": "alpha-local",
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
        environment="alpha",
        target="alpha-local",
        device_id="emulator-5554",
        attempt_path=attempt_path,
        report_path=report_path,
        output_root=output_root,
        app_root=projected_app,
        launch_control=control,
    )
    base_environment = {
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "PATH": os.environ["PATH"],
        **child_environment,
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


@pytest.mark.parametrize(
    "launch_provenance",
    (
        "canonical_launcher",
        "workspace_flutter_run",
    ),
)
def test_real_run_sh_warning_branches_reach_supervisor_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_provenance: str,
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
        projection_root=output_root / "warning/source-projection",
        evidence_path=output_root / "warning/source-projection.json",
    )
    projected_root = Path(projection["sourceProjectionRoot"])
    projected_app = projected_root / "quwoquan_app"
    fake_flutter = tmp_path / "bin/flutter"
    fake_flutter.parent.mkdir(parents=True)
    fake_flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_flutter.chmod(0o755)

    resolver = projected_app / "scripts/tools/flutter_facade/resolve_real_flutter.py"
    resolver.parent.mkdir(parents=True)
    resolver.write_text(
        "import json, os\n"
        "print(json.dumps({"
        "'executable': os.environ['QWQ_TEST_FAKE_FLUTTER'], "
        "'flutterVersion': '3.35.1', "
        f"'commandResolutionDigest': {_digest('9')!r}"
        "}))\n",
        encoding="utf-8",
    )
    ops_lib = projected_root / "quwoquan_ops/cli/lib"
    ops_lib.mkdir(parents=True, exist_ok=True)
    (ops_lib / "app_debug_preflight_handoff.py").write_text(
        "def app_debug_preflight_purpose(run_mode):\n"
        "    return 'content_live' if run_mode == 'content-live' else 'runtime'\n",
        encoding="utf-8",
    )
    (ops_lib / "dev_up.py").write_text(
        "def find_device(*_args, **_kwargs):\n"
        "    return {'targetPlatform': 'android-arm64', 'emulator': True}\n"
        "def detect_device_kind(*_args, **_kwargs):\n"
        "    return 'android_emulator'\n"
        "def load_environment_topology():\n"
        "    return {}\n"
        "def resolve_app_endpoint_overrides(*_args, **_kwargs):\n"
        "    return {key: 'http://127.0.0.1:1' for key in ("
        "'gatewayBaseUrl', 'legalBaseUrl', 'mediaAvatarBaseUrl', "
        "'mediaImageBaseUrl', 'mediaVideoBaseUrl', 'mediaUploadBaseUrl')}\n"
        "def enable_android_adb_reverse(*_args, **_kwargs):\n"
        "    raise RuntimeError('synthetic reverse failure')\n",
        encoding="utf-8",
    )
    (ops_lib / "app_identity.py").write_text(
        "def application_id_for(*_args):\n"
        "    return 'com.leadwise.quwoquan.nonprod.debug'\n",
        encoding="utf-8",
    )
    stackctl = projected_root / "quwoquan_ops/cli/stackctl.py"
    stackctl.write_text(
        "import json, sys\n"
        "if 'app-debug-preflight' in sys.argv:\n"
        "    print(json.dumps({"
        "'purpose': 'content_live', 'status': 'passed', "
        "'nonPromotable': True, 'warnings': []}))\n"
        "    raise SystemExit(0)\n"
        "if 'device-trust' in sys.argv:\n"
        "    raise SystemExit(19)\n"
        "raise SystemExit(23)\n",
        encoding="utf-8",
    )
    python_resolver = projected_app / "scripts/ios/build_resolve_stackctl_python.sh"
    python_resolver.parent.mkdir(parents=True, exist_ok=True)
    python_resolver.write_text(
        f"#!/bin/sh\nprintf '%s\\n' {sys.executable!r}\n",
        encoding="utf-8",
    )
    python_resolver.chmod(0o755)
    handoff = projected_app / "scripts/device/build_launcher_handoff.py"
    handoff.write_text(
        "import json, pathlib, sys\n"
        "trust = pathlib.Path(sys.argv[sys.argv.index("
        "'--runtime-config-trust-output') + 1])\n"
        "trust.write_text('{}\\n', encoding='utf-8')\n"
        "launch_provenance = sys.argv[sys.argv.index("
        "'--launch-provenance') + 1]\n"
        "print(json.dumps({"
        "'entrypoint': 'lib/main_nonprod.dart', "
        "'launchProvenance': launch_provenance, "
        "'runtimeConfigSupplyMode': 'external_runtime_package', "
        f"'runtimeConfigPackageDigest': {_digest('4')!r}, "
        f"'runtimeConfigTrustEnvelopeDigest': {_digest('3')!r}, "
        f"'effectiveLaunchManifestDigest': {_digest('5')!r}"
        "}))\n",
        encoding="utf-8",
    )
    supervisor_capture = tmp_path / "supervisor-argv.json"
    supervisor = projected_app / "scripts/device/supervise_app_launch.py"
    supervisor.write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['QWQ_TEST_SUPERVISOR_CAPTURE']).write_text("
        "json.dumps({'argv': sys.argv[1:], 'startupTerminalReceipt': "
        "os.environ.get('QWQ_APP_STARTUP_TERMINAL_RECEIPT', '')}), "
        "encoding='utf-8')\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    dependency_prep = projected_app / "scripts/device/prepare_flutter_dependencies.py"
    dependency_prep.write_text(
        "import pathlib, shlex, sys\n"
        "root = pathlib.Path(sys.argv[sys.argv.index('--projection-root') + 1])\n"
        "state = pathlib.Path(sys.argv[sys.argv.index('--private-state-root') + 1])\n"
        "cache = root / 'quwoquan_app/.dart_tool/qwq_pub_cache'\n"
        "home = state / 'flutter/production/home'\n"
        "xdg_config = state / 'flutter/production/xdg-config'\n"
        "xdg_cache = state / 'flutter/production/xdg-cache'\n"
        "gradle = root / 'quwoquan_app/.dart_tool/qwq_android_gradle_dependency/home'\n"
        "expectation = state / 'dependency-projection-expectation.json'\n"
        "prebuild = state / 'dependency-projection-prebuild-readback.json'\n"
        "[path.mkdir(parents=True, exist_ok=True) for path in "
        "(cache, home, xdg_config, xdg_cache, gradle)]\n"
        "expectation.write_text('{}\\n', encoding='utf-8')\n"
        "prebuild.write_text('{}\\n', encoding='utf-8')\n"
        "values = {"
        "'PUB_CACHE': cache, 'GRADLE_USER_HOME': gradle, 'HOME': home, "
        "'XDG_CONFIG_HOME': xdg_config, 'XDG_CACHE_HOME': xdg_cache}\n"
        "[print('export ' + key + '=' + shlex.quote(str(value))) "
        "for key, value in values.items()]\n"
        "print('export FLUTTER_SWIFT_PACKAGE_MANAGER=false')\n"
        "print('export GIT_CONFIG_GLOBAL=/dev/null')\n"
        "print('export GIT_CONFIG_NOSYSTEM=1')\n"
        "print('export GIT_TERMINAL_PROMPT=0')\n"
        "print('export QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF=' "
        "+ shlex.quote(str(expectation)))\n"
        f"print('export QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST={_digest('6')}')\n"
        "print('export QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF=' "
        "+ shlex.quote(str(prebuild)))\n"
        f"print('export QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST={_digest('7')}')\n",
        encoding="utf-8",
    )
    launch_arguments = [
        "bash",
        "run.sh",
        "--mode",
        "content-live",
        "-d",
        "device",
    ]
    process = subprocess.run(
        launch_arguments,
        cwd=projected_app,
        env={
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "PATH": os.environ["PATH"],
            "QWQ_OUTPUT_ROOT": str(output_root),
            "QWQ_TEST_FAKE_FLUTTER": str(fake_flutter),
            "QWQ_TEST_SUPERVISOR_CAPTURE": str(supervisor_capture),
            "QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST": str(manifest_path),
            "QWQ_APP_LAUNCH_PROVENANCE": launch_provenance,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert process.returncode != 0
    assert supervisor_capture.is_file(), (
        f"stdout={process.stdout}\nstderr={process.stderr}"
    )
    supervisor_capture_payload = json.loads(
        supervisor_capture.read_text(encoding="utf-8")
    )
    supervisor_argv = supervisor_capture_payload["argv"]
    warnings = [
        supervisor_argv[index + 1]
        for index, value in enumerate(supervisor_argv[:-1])
        if value == "--warning"
    ]
    assert any("content delivery verification skipped" in item for item in warnings)
    assert any(
        "Android transport preparation is unavailable" in item for item in warnings
    )
    assert any(
        "target-bound transport trust is unavailable" in item for item in warnings
    )
    assert any("Android reverse ports are unavailable" in item for item in warnings)
    assert "--require-safe-terminal" in supervisor_argv
    terminal_index = supervisor_argv.index("--startup-terminal-receipt")
    terminal_receipt = Path(supervisor_argv[terminal_index + 1])
    attempt_index = supervisor_argv.index("--receipt")
    launch_attempt = Path(supervisor_argv[attempt_index + 1])
    assert terminal_receipt.is_absolute()
    assert terminal_receipt.parent == launch_attempt.parent
    assert terminal_receipt.name == "startup-terminal.json"
    assert supervisor_capture_payload["startupTerminalReceipt"] == str(terminal_receipt)
    provenance_index = supervisor_argv.index("--launch-provenance")
    assert supervisor_argv[provenance_index + 1] == launch_provenance
    assert not terminal_receipt.exists()
    teardown_receipts = list(output_root.rglob("teardown.json"))
    assert len(teardown_receipts) == 1
    teardown = json.loads(teardown_receipts[0].read_text(encoding="utf-8"))
    assert teardown["schema"] == "quwoquan_app.launch_teardown.v1"
    assert teardown["status"] == "passed"
    assert teardown["warnings"] == []


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
            "--mode",
            "content-live",
            "-d",
            "device",
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
    assert "not bound to the original workspace projection handoff" in (process.stderr)
    assert not supervisor_capture.exists()

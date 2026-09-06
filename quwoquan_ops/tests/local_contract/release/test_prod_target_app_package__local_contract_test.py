from __future__ import annotations

import contextlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

from quwoquan_ops.cli import stackctl


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
ROOT = Path(__file__).resolve().parents[4]
PREPARE_INPUTS = ROOT / "quwoquan_ops/gate/prepare_environment_packaging_contract_inputs.py"
CLEANUP_WORKSPACE = ROOT / "quwoquan_ops/gate/cleanup_deployment_test_workspace.py"
PROD_APP_SOURCE = ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml"
BUILD_APP_PACKAGE = ROOT / "quwoquan_app/scripts/env/build_app_env_package.sh"
VERIFY_PROD_PURITY = ROOT / "quwoquan_app/scripts/env/verify_prod_package_purity.py"


def test_prod_app_packages_block_on_unapproved_legal_identity_without_mutating_source(
    tmp_path: Path,
) -> None:
    deploy_root = Path(tempfile.gettempdir()) / (
        "quwoquan-deploy." + secrets.token_hex(3)
    )
    deploy_root.mkdir(mode=0o700)
    output_root = tmp_path / "output"
    subprocess.run(
        [sys.executable, str(PREPARE_INPUTS), str(deploy_root)],
        cwd=ROOT,
        check=True,
    )
    release_attestation = deploy_root / "candidate-release.json"
    rollback_release_attestation = deploy_root / "rollback-release.json"
    source_before = PROD_APP_SOURCE.read_bytes()
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
            "QWQ_OUTPUT_ROOT": str(output_root),
            "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_KEY_ID": "packaging-contract",
            "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_PRIVATE_KEY_FILE": str(
                deploy_root / "graphql-signing-private.pem"
            ),
            "QWQ_GRAPHQL_READ_REGISTRY_TRUSTED_PUBLIC_KEYS_FILE": str(
                deploy_root / "graphql-trusted-public-keys.json"
            ),
        }
    )

    try:
        for target in ("prod-sim", "prod-hosted"):
            report_dir = output_root / "env/prod/runs" / f"legal-identity-{target}"
            args = stackctl.build_parser().parse_args(
                [
                    "package",
                    "--env",
                    "prod",
                    "--target",
                    target,
                    "--release-attestation",
                    str(release_attestation),
                    "--rollback-release-attestation",
                    str(rollback_release_attestation),
                    "--report-dir",
                    str(report_dir),
                ]
            )
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": []},
                ),
                mock.patch.object(
                    stackctl,
                    "materialize_package_input_capsule",
                    return_value=None,
                ),
                mock.patch.object(
                    stackctl,
                    "_run_runtime_compile_preflight",
                    return_value=([], ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_target_package_lock",
                    return_value=contextlib.nullcontext(),
                ),
            ):
                result = stackctl.command_package(args)

            assert result["exitCode"] == 1, result
            assert result["summary"] == "stackctl package failed for legal-static/prod"
            assert "placeholder text" in "\n".join(result["details"])
            assert not (deploy_root / target / "active-candidate.json").exists()

        assert PROD_APP_SOURCE.read_bytes() == source_before
    finally:
        subprocess.run(
            [sys.executable, str(CLEANUP_WORKSPACE), str(deploy_root)],
            cwd=ROOT,
            check=True,
        )


def test_prod_sim_app_package_materializes_isolated_sim_public_bases_and_purity(
    tmp_path: Path,
) -> None:
    deploy_root = tmp_path / "deploy"
    output_root = tmp_path / "output"
    deploy_root.mkdir()
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
        "QWQ_OUTPUT_ROOT": str(output_root),
        "QWQ_DEPLOY_TARGET": "prod-sim",
        "QWQ_PACKAGE_SOURCE_REVISION": "c" * 40,
    }

    result = subprocess.run(
        ["bash", str(BUILD_APP_PACKAGE), "--env", "prod"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    package_root = deploy_root / "prod-sim/packages/app"
    runtime = json.loads(
        (package_root / "environment_runtime.yaml").read_text(encoding="utf-8")
    )
    report = json.loads(
        (package_root / "report.json").read_text(encoding="utf-8")
    )
    assert runtime["environment"] == "prod"
    assert runtime["target"] == "prod-sim"
    assert report["target"] == "prod-sim"
    assert report["composition"] == "production_remote"
    assert not (deploy_root / "prod-hosted").exists()
    for value in runtime["publicBases"].values():
        hostname = urlparse(str(value)).hostname or ""
        assert hostname == "sim.quwoquan.com" or hostname.endswith(
            ".sim.quwoquan.com"
        ), value

    purity = subprocess.run(
        [
            sys.executable,
            str(VERIFY_PROD_PURITY),
            "--scope",
            "app",
            "--target",
            "prod-sim",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert purity.returncode == 0, purity.stdout + purity.stderr

    with (package_root / "app_runtime.yaml").open("a", encoding="utf-8") as stream:
        stream.write("test_fixtures: forbidden\\n")
    rejected = subprocess.run(
        [
            sys.executable,
            str(VERIFY_PROD_PURITY),
            "--scope",
            "app",
            "--target",
            "prod-sim",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 1
    assert "contains forbidden token 'test_fixtures'" in rejected.stdout

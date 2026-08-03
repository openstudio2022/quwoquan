from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.gate import verify_env_artifact_isolation as isolation
from quwoquan_ops.gate import verify_environment_packaging_contract as packaging


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _recipe(target: str) -> str:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    start = makefile.index(f"{target}:")
    end = makefile.find("\n\n", start)
    return makefile[start:] if end == -1 else makefile[start:end]


def test_runtime_shared_package_requires_complete_provenance_and_digests(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "runtime-shared"
    package_dir.mkdir()
    files: dict[str, dict[str, str]] = {}
    for name in sorted(packaging.RUNTIME_SHARED_FILES):
        path = package_dir / name
        path.write_text(f"{name}\n", encoding="utf-8")
        files[name] = {
            "source": f"quwoquan_service/runtime/reliabletask/resources/{name}",
            "sha256": _sha256(path),
        }
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "qwq.runtime_shared_package",
                "environment": "beta",
                "provenance": {"files": files},
            }
        ),
        encoding="utf-8",
    )

    assert packaging.validate_runtime_shared_package(
        package_dir,
        "beta",
        "beta-local",
    ) == []

    (package_dir / "module_catalog.yaml").write_text("tampered\n", encoding="utf-8")
    assert any(
        "digest mismatch for module_catalog.yaml" in issue
        for issue in packaging.validate_runtime_shared_package(
            package_dir,
            "beta",
            "beta-local",
        )
    )


def test_legal_static_package_checksums_and_portal_provenance_are_fail_closed(
    tmp_path: Path,
) -> None:
    legal_root = tmp_path / "legal-static"
    legal_package = legal_root / "2026-07"
    public_manifest = legal_package / "public" / "legal" / "manifest.json"
    public_manifest.parent.mkdir(parents=True)
    public_manifest.write_text("{}\n", encoding="utf-8")
    release_metadata = legal_package / "release_metadata.json"
    release_metadata.write_text(
        json.dumps({"packageKind": "legal-static", "env": "beta"}),
        encoding="utf-8",
    )
    legal_checksums = {
        "public/legal/manifest.json": _sha256(public_manifest),
        "release_metadata.json": _sha256(release_metadata),
    }
    (legal_package / "checksums.json").write_text(
        json.dumps(legal_checksums),
        encoding="utf-8",
    )
    legal_root.mkdir(exist_ok=True)
    (legal_root / "current").symlink_to(legal_package.name)

    assert packaging.validate_legal_static_package(legal_root, "beta") == []
    public_manifest.write_text('{"tampered":true}\n', encoding="utf-8")
    assert any(
        "digest mismatch for public/legal/manifest.json" in issue
        for issue in packaging.validate_legal_static_package(legal_root, "beta")
    )

    portal_root = tmp_path / "ops-portal"
    staging_package = portal_root / "staging"
    dist = staging_package / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>\n", encoding="utf-8")
    package_digest = packaging._sha256_tree(dist)
    portal_package = portal_root / package_digest.removeprefix("sha256:")
    staging_package.rename(portal_package)
    dist = portal_package / "dist"
    manifest_path = portal_package / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "qwq.ops_portal_application",
                "packageDigest": package_digest,
                "sourceGitSha": "a" * 40,
                "sourceTreeDigest": "sha1:" + ("b" * 40),
                "opsBaseUrl": "https://ops.example.test",
                "contentBaseUrl": "https://api.example.test",
                "entityBaseUrl": "https://api.example.test",
                "oidcIssuer": "https://issuer.example.test",
                "oidcClientId": "ops-portal",
            }
        ),
        encoding="utf-8",
    )
    provenance = {
        "schema": "qwq.ops_portal_package",
        "packageKind": "ops-portal",
        "environment": "prod",
        "target": "prod-hosted",
        "packageDigest": package_digest,
        "gitRevision": "a" * 40,
        "digests": {
            "manifest": _sha256(manifest_path),
            "distTree": packaging._sha256_tree(dist),
        },
    }
    (portal_package / "provenance.json").write_text(
        json.dumps(provenance),
        encoding="utf-8",
    )
    portal_root.mkdir(exist_ok=True)
    (portal_root / "current").symlink_to(portal_package.name)

    assert (
        packaging.validate_ops_portal_package(
            portal_root,
            "prod",
            target="prod-hosted",
        )
        == []
    )
    (dist / "index.html").write_text("<html>tampered</html>\n", encoding="utf-8")
    assert any(
        "digest mismatch for distTree" in issue
        for issue in packaging.validate_ops_portal_package(
            portal_root,
            "prod",
            target="prod-hosted",
        )
    )


def test_package_boundary_and_isolation_include_every_package_kind(
    tmp_path: Path,
) -> None:
    deployment_root = tmp_path / "deploy" / "beta-local" / "packages"
    app_dir = deployment_root / "app"
    shared_dir = deployment_root / "runtime-shared"
    legal_dir = deployment_root / "legal-static"
    portal_dir = deployment_root / "ops-portal"
    for directory, name in (
        (app_dir, "app.txt"),
        (shared_dir, "shared.txt"),
        (portal_dir, "portal.txt"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text("beta-only", encoding="utf-8")
    legal_manifest = legal_dir / "current" / "public" / "legal" / "manifest.json"
    legal_manifest.parent.mkdir(parents=True)
    legal_manifest.write_text(
        '{"env":"beta","legalBaseUrl":"https://beta.example.test/legal"}\n',
        encoding="utf-8",
    )

    assert packaging.package_output_boundary_issues(shared_dir, deployment_root) == []
    output_path = tmp_path / ".qwq_output" / "env" / "beta" / "packages"
    assert packaging.package_output_boundary_issues(output_path, deployment_root)

    with (
        mock.patch.object(
            isolation,
            "app_deployment_package_dir",
            return_value=app_dir,
        ),
        mock.patch.object(
            isolation,
            "deployment_package_root",
            return_value=deployment_root,
        ),
        mock.patch.object(
            isolation,
            "runtime_shared_deployment_package_dir",
            return_value=shared_dir,
        ),
        mock.patch.object(
            isolation,
            "legal_static_deployment_package_dir",
            return_value=legal_dir,
        ),
        mock.patch.object(
            isolation,
            "portal_deployment_package_dir",
            return_value=portal_dir,
        ),
    ):
        names = {
            path.name
            for path in isolation.artifact_files("beta", target_name="beta-local")
        }
    assert names == {"app.txt", "shared.txt", "manifest.json", "portal.txt"}


def test_product_telemetry_package_rejects_resolved_credentials(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "product-ops-service"
    config_dir = package_dir / "config"
    config_dir.mkdir(parents=True)
    config = config_dir / "config.yaml"
    config.write_text(
        "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT: https://logs.prod.example\n"
        "PRODUCT_OPS_ELASTICSEARCH_API_KEY: ${PRODUCT_OPS_ELASTICSEARCH_API_KEY:-}\n",
        encoding="utf-8",
    )
    assert packaging.validate_product_telemetry_secret_package(package_dir) == []

    config.write_text(
        "- name: PRODUCT_OPS_ELASTICSEARCH_API_KEY\n"
        "  value: fixture-value-must-not-package\n",
        encoding="utf-8",
    )
    assert any(
        "PRODUCT_OPS_ELASTICSEARCH_API_KEY" in issue
        for issue in packaging.validate_product_telemetry_secret_package(package_dir)
    )


def test_public_make_targets_delegate_environment_operations_to_stackctl() -> None:
    assert "feature_tree.py verify --changes" in _recipe("verify-feature-tree")
    for target in (
        "beta-up",
        "beta-down",
        "beta-status",
        "config-slo-gate",
        "deploy-beta-k8s",
    ):
        recipe = _recipe(target)
        assert "quwoquan_ops/cli/stackctl.py" in recipe
        assert "bash quwoquan_ops/cli/" not in recipe


def test_stackctl_rejects_missing_portal_oidc_and_has_no_private_prod_state_writer(
    tmp_path: Path,
) -> None:
    missing_portal_args = stackctl.build_parser().parse_args(
        [
            "package",
            "--env",
            "prod",
            "--kind",
            "ops-portal",
        ]
    )
    with (
        mock.patch.dict(
            "os.environ",
            {"QWQ_DEPLOY_WORK_ROOT": str(tmp_path / "deploy")},
        ),
        mock.patch.object(stackctl, "resolve_report_dir", return_value=tmp_path / "portal-report"),
        mock.patch.object(stackctl, "_write_summary_bundle"),
        mock.patch.object(stackctl, "relpath", side_effect=str),
    ):
        portal_result = stackctl.command_package(missing_portal_args)
    assert portal_result["exitCode"] == 2
    assert any("OIDC values" in detail for detail in portal_result["details"])

    deploy_modes = stackctl.build_parser().parse_args(
        ["deploy", "--target", "prod-hosted", "--dry-run", "true"]
    )
    assert deploy_modes.mode == ""
    stackctl_source = (ROOT / "quwoquan_ops/cli/stackctl.py").read_text(
        encoding="utf-8"
    )
    assert '"config-gray"' not in stackctl_source
    assert '"config-rollback"' not in stackctl_source


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temporary:
        test_runtime_shared_package_requires_complete_provenance_and_digests(
            Path(temporary)
        )
    with tempfile.TemporaryDirectory() as temporary:
        test_legal_static_package_checksums_and_portal_provenance_are_fail_closed(
            Path(temporary)
        )
    with tempfile.TemporaryDirectory() as temporary:
        test_package_boundary_and_isolation_include_every_package_kind(Path(temporary))
    test_public_make_targets_delegate_environment_operations_to_stackctl()
    with tempfile.TemporaryDirectory() as temporary:
        test_stackctl_rejects_missing_portal_oidc_and_routes_private_config_script(
            Path(temporary)
        )

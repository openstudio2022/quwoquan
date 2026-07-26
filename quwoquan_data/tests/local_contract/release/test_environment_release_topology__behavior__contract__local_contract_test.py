"""Environment-owned Data release target resolution contract."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.environment.topology import EnvironmentReleaseMode, resolve_environment_release_target
from content.release.model import DeploymentEnvironment


def test_local_release_targets_derive_ports_and_paths_from_ops_topology() -> None:
    beta = resolve_environment_release_target(DeploymentEnvironment.BETA)
    gamma = resolve_environment_release_target(DeploymentEnvironment.GAMMA)

    assert beta.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert beta.mongo_uri == "mongodb://127.0.0.1:18410/?directConnection=true"
    assert beta.media_sync_root is not None
    assert beta.media_sync_root.as_posix().endswith("/env/beta/local/beta-local/cache/media")
    assert gamma.mongo_uri == "mongodb://127.0.0.1:19410/?directConnection=true"
    assert gamma.media_sync_root is not None
    assert gamma.media_sync_root.as_posix().endswith("/env/gamma/local/gamma-local/cache/media")


def test_alpha_release_target_is_local_import() -> None:
    target = resolve_environment_release_target(DeploymentEnvironment.ALPHA)

    assert target.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert target.import_ready is True
    assert target.mongo_uri == "mongodb://127.0.0.1:17410/?directConnection=true"
    assert target.media_sync_root is not None
    assert target.media_sync_root.as_posix().endswith("/env/alpha/local/alpha-local/cache/media")


def test_prod_target_reports_only_missing_secret_key_names(monkeypatch) -> None:
    env_keys = (
        "QWQ_PROD_DATA_RELEASE_MONGO_URI",
        "QWQ_PROD_DATA_RELEASE_MEDIA_ROOT",
    )
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)

    target = resolve_environment_release_target(DeploymentEnvironment.PROD)

    assert target.mode is EnvironmentReleaseMode.HOSTED_IMPORT
    assert target.missing_requirements == env_keys
    assert target.mongo_uri == ""
    assert target.media_sync_root is None

"""Environment-owned Data release target resolution contract."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.environment.topology import (
    EnvironmentReleaseMode,
    MediaDeliverySlice,
    resolve_environment_release_target,
)
from content.release.model import DeploymentEnvironment


def test_local_release_targets_derive_ports_and_paths_from_ops_topology() -> None:
    beta = resolve_environment_release_target(DeploymentEnvironment.BETA)
    gamma = resolve_environment_release_target(DeploymentEnvironment.GAMMA)

    assert beta.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert beta.mongo_uri == "mongodb://127.0.0.1:18410/?directConnection=true"
    assert beta.redis_addr == "127.0.0.1:18420"
    assert beta.redis_database == 1
    assert beta.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@127.0.0.1:18400/quwoquan?sslmode=disable"
    )
    assert beta.media_sync_root is not None
    assert beta.media_sync_root.as_posix().endswith("/env/beta/local/beta-local/cache/media")
    assert beta.api_base_url == "https://api.beta.quwoquan.com:18000"
    assert beta.media_delivery_base_url == "https://cdn.beta.quwoquan.com:18100"
    assert beta.media_base_url(MediaDeliverySlice.AVATAR).endswith("/media/avatar")
    assert gamma.mongo_uri == "mongodb://127.0.0.1:19410/?directConnection=true"
    assert gamma.redis_addr == "127.0.0.1:19420"
    assert gamma.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@127.0.0.1:19400/quwoquan?sslmode=disable"
    )
    assert gamma.media_sync_root is not None
    assert gamma.media_sync_root.as_posix().endswith("/env/gamma/local/gamma-local/cache/media")
    assert gamma.api_base_url == "https://api.gamma.quwoquan.com:19000"
    assert gamma.media_delivery_base_url == "https://cdn.gamma.quwoquan.com:19100"


def test_alpha_release_target_is_local_import() -> None:
    target = resolve_environment_release_target(DeploymentEnvironment.ALPHA)

    assert target.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert target.import_ready is True
    assert target.mongo_uri == "mongodb://127.0.0.1:17410/?directConnection=true"
    assert target.redis_addr == "127.0.0.1:17420"
    assert target.redis_database == 1
    assert target.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@127.0.0.1:17400/quwoquan?sslmode=disable"
    )
    assert target.media_sync_root is not None
    assert target.media_sync_root.as_posix().endswith("/env/alpha/local/alpha-local/cache/media")
    assert target.api_base_url == "https://api.alpha.quwoquan.com:17000"
    assert target.media_delivery_base_url == "https://cdn.alpha.quwoquan.com:17100"


def test_prod_target_reports_only_missing_secret_key_names(monkeypatch) -> None:
    env_keys = (
        "QWQ_PROD_DATA_RELEASE_MONGO_URI",
        "QWQ_PROD_DATA_RELEASE_REDIS_ADDR",
        "QWQ_PROD_DATA_RELEASE_USER_POSTGRES_DSN",
        "QWQ_PROD_DATA_RELEASE_MEDIA_ROOT",
    )
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)

    target = resolve_environment_release_target(DeploymentEnvironment.PROD)

    assert target.mode is EnvironmentReleaseMode.HOSTED_IMPORT
    assert target.missing_requirements == env_keys
    assert target.mongo_uri == ""
    assert target.redis_addr == ""
    assert target.user_postgres_dsn == ""
    assert target.media_sync_root is None
    assert target.api_base_url == "https://api.quwoquan.com"
    assert target.media_delivery_base_url == "https://cdn.quwoquan.com"

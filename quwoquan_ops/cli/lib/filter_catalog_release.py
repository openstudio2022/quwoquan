"""stackctl 的 FilterCatalogRelease 发布面执行边界。"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

from .local_environment_auth import open_local_acceptance_session


PUBLISH_TOKEN_ENV_DEFAULT = "QWQ_FILTER_CATALOG_PUBLISH_TOKEN"
LOCAL_FILTER_CATALOG_TARGETS = {
    "beta-local": "beta",
    "gamma-local": "gamma",
}
MUTATING_ACTIONS = {"stage", "activate", "stage-and-activate", "rollback"}


@dataclass(frozen=True)
class FilterCatalogCommandExecution:
    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str


def execute_filter_catalog_command(
    *,
    repo_root: Path,
    target_name: str,
    environment: str,
    api_base_url: str,
    action: str,
    rollback_release_id: str,
    token_env: str,
    prod_gray_activation: bool,
) -> FilterCatalogCommandExecution:
    """以 target 绑定的身份调用唯一 Data CLI，不泄漏 bearer token。"""
    if action not in {
        "stage",
        "activate",
        "stage-and-activate",
        "verify",
        "rollback",
    }:
        raise ValueError(f"unsupported filter catalog action: {action}")
    normalized_token_env = _token_env_name(token_env)
    process_env = os.environ.copy()
    local_environment = LOCAL_FILTER_CATALOG_TARGETS.get(target_name)
    if action in MUTATING_ACTIONS:
        if local_environment is not None:
            session = open_local_acceptance_session(
                api_base_url,
                environment=local_environment,
                target_name=target_name,
                subject=f"filter-catalog-{local_environment}-publisher",
                profile="content-filter-catalog-publisher",
            )
            process_env[normalized_token_env] = session.access_token
        elif target_name == "prod-hosted":
            token = process_env.get(normalized_token_env, "").strip()
            if not token:
                raise ValueError(
                    f"prod FilterCatalogRelease mutation requires {normalized_token_env}"
                )
        else:
            raise ValueError(
                f"FilterCatalogRelease publish target is unsupported: {target_name}"
            )

    argv = [
        sys.executable,
        "quwoquan_data/scripts/cli.py",
        "filter-catalog",
        "publish",
        "--environment",
        environment,
        "--base-url",
        api_base_url,
        "--action",
        action,
        "--token-env",
        normalized_token_env,
    ]
    if rollback_release_id.strip():
        argv.extend(["--rollback-release-id", rollback_release_id.strip()])
    if target_name in LOCAL_FILTER_CATALOG_TARGETS:
        argv.append("--insecure-local-tls")
    if prod_gray_activation:
        argv.append("--prod-gray-activation")
    result = subprocess.run(
        argv,
        cwd=repo_root,
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return FilterCatalogCommandExecution(
        argv=tuple(argv),
        return_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _token_env_name(value: str) -> str:
    name = value.strip()
    if not name:
        return PUBLISH_TOKEN_ENV_DEFAULT
    if (
        not (name[0].isalpha() or name[0] == "_")
        or any(not (character.isalnum() or character == "_") for character in name)
    ):
        raise ValueError("FilterCatalogRelease token environment variable name is invalid")
    return name

"""stackctl 的 FilterCatalogRelease 发布面执行边界。"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

PUBLISH_TOKEN_ENV_DEFAULT = "QWQ_FILTER_CATALOG_PUBLISH_TOKEN"
LOCAL_FILTER_CATALOG_TARGETS = {
    "alpha-local": "alpha",
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
    token_value: str = "",
    ssl_cafile: str = "",
    diagnostic_log_path: Path | None = None,
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
    normalized_cafile = str(ssl_cafile or "").strip()
    if normalized_cafile:
        ca_path = Path(normalized_cafile).expanduser()
        if not ca_path.is_absolute() or not ca_path.is_file() or ca_path.is_symlink():
            raise ValueError("FilterCatalogRelease TLS CA file is invalid")
        process_env["SSL_CERT_FILE"] = str(ca_path)
    if action in MUTATING_ACTIONS:
        if target_name in {*LOCAL_FILTER_CATALOG_TARGETS, "prod-hosted"}:
            token = str(token_value or "").strip() or process_env.get(
                normalized_token_env,
                "",
            ).strip()
            if not token:
                raise ValueError(
                    "FilterCatalogRelease mutation requires a protected canonical "
                    f"publisher token in {normalized_token_env}"
                )
            process_env[normalized_token_env] = token
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
    if diagnostic_log_path is not None:
        if result.returncode == 0:
            diagnostic_log_path.unlink(missing_ok=True)
        else:
            _write_diagnostic_log(
                diagnostic_log_path,
                stdout=result.stdout,
                stderr=result.stderr,
                secrets=(process_env.get(normalized_token_env, ""),),
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


def _write_diagnostic_log(
    path: Path,
    *,
    stdout: str,
    stderr: str,
    secrets: tuple[str, ...],
) -> None:
    rendered = "\n".join(
        part.rstrip("\n")
        for part in (
            "[stdout]\n" + stdout,
            "[stderr]\n" + stderr,
        )
        if part
    ).rstrip() + "\n"
    for secret in secrets:
        if secret:
            rendered = rendered.replace(secret, "***")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(rendered, encoding="utf-8")
    os.chmod(path, 0o600)

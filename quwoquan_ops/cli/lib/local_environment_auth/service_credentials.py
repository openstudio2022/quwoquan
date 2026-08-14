"""本地服务/运营者短时 JWT 铸造（逐字搬移）。

测试通过 ``mock.patch.object(local_environment_auth, "prepare_local_environment_auth")``
与 ``mock.patch.object(local_environment_auth.subprocess, "run")`` 拦截铸造流程，
因此二者在本模块内一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.local_environment_auth as _pkg

from .constants import _REPO_ROOT
from .guards import _require_local_environment


def mint_local_filter_catalog_service_token(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> str:
    """Mint one 30-minute qwq-data token through the canonical Go signer."""

    auth = _pkg.prepare_local_environment_auth(
        environment,
        target_name,
        deployment_work_root=deployment_work_root,
    )
    process_environment = {
        **os.environ,
        **auth.environment,
        "GOCACHE": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-build/local-service-credential"
        ),
        "GOTMPDIR": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-tmp/local-service-credential"
        ),
    }
    Path(process_environment["GOCACHE"]).mkdir(parents=True, exist_ok=True)
    Path(process_environment["GOTMPDIR"]).mkdir(parents=True, exist_ok=True)
    result = _pkg.subprocess.run(
        ["go", "run", "./cmd/local-filter-catalog-credential"],
        cwd=_REPO_ROOT / "quwoquan_service",
        env=process_environment,
        text=True,
        stdout=_pkg.subprocess.PIPE,
        stderr=_pkg.subprocess.PIPE,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or "\n" in token:
        raise RuntimeError(
            "local FilterCatalog service credential mint failed"
            + (f" (exit={result.returncode})" if result.returncode else "")
        )
    claims = _decode_local_jwt_claims(
        token,
        label="local FilterCatalog service credential",
    )
    if (
        claims.get("sub") != "service:qwq-data"
        or claims.get("roles") != ["service"]
        or "content.filter_catalog.manage"
        not in str(claims.get("scope") or "").split()
        or claims.get("iss") != auth.environment["AUTH_JWT_ISSUER"]
        or claims.get("aud") != auth.environment["AUTH_JWT_AUDIENCE"]
        or not isinstance(claims.get("iat"), int)
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] - claims["iat"] != 30 * 60
    ):
        raise RuntimeError(
            "local FilterCatalog service credential claims mismatch"
        )
    return token


def mint_local_product_ops_operator_token(
    environment: str,
    target_name: str,
    *,
    deployment_work_root: str | Path | None = None,
) -> str:
    """Mint one 15-minute Alpha/Beta/Gamma Product Ops operator credential.

    Prod and every non-local target must use the real RS256 OIDC path and are
    rejected before the canonical signer is invoked.
    """

    _require_local_environment(environment, target_name)
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "local Product Ops operator credential is limited to Alpha/Beta/Gamma"
        )
    auth = _pkg.prepare_local_environment_auth(
        environment,
        target_name,
        deployment_work_root=deployment_work_root,
    )
    process_environment = {
        **os.environ,
        **auth.environment,
        "APP_ENV": environment,
        "GOCACHE": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-build/local-operator-credential"
        ),
        "GOTMPDIR": str(
            _REPO_ROOT
            / ".qwq_output/env/repo/local/go-tmp/local-operator-credential"
        ),
    }
    Path(process_environment["GOCACHE"]).mkdir(parents=True, exist_ok=True)
    Path(process_environment["GOTMPDIR"]).mkdir(parents=True, exist_ok=True)
    result = _pkg.subprocess.run(
        ["go", "run", "./cmd/local-product-ops-operator-credential"],
        cwd=_REPO_ROOT / "quwoquan_service",
        env=process_environment,
        text=True,
        stdout=_pkg.subprocess.PIPE,
        stderr=_pkg.subprocess.PIPE,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token or "\n" in token:
        raise RuntimeError(
            "local Product Ops operator credential mint failed"
            + (f" (exit={result.returncode})" if result.returncode else "")
        )
    claims = _decode_local_jwt_claims(
        token,
        label="local Product Ops operator credential",
    )
    expected_subject = f"operator:content-commercial:{environment}"
    if (
        claims.get("sub") != expected_subject
        or claims.get("roles") != ["operator"]
        or str(claims.get("scope") or "").split()
        != [
            "ops.experiment.read",
            "ops.experiment.write",
            "ops.product.dashboard.read",
            "ops.reco.read",
            "ops.reco.write",
            "ops.telemetry.read",
        ]
        or claims.get("iss") != auth.environment["AUTH_JWT_ISSUER"]
        or claims.get("aud") != auth.environment["AUTH_JWT_AUDIENCE"]
        or not isinstance(claims.get("iat"), int)
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] - claims["iat"] != 15 * 60
    ):
        raise RuntimeError(
            "local Product Ops operator credential claims mismatch"
        )
    return token


def _decode_local_jwt_claims(token: str, *, label: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError(f"{label} is not a JWT")
    try:
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(
            base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        )
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} claims are invalid") from exc
    if not isinstance(claims, dict):
        raise RuntimeError(f"{label} claims are invalid")
    return claims

"""Verify every imported Gamma homepage through the public read API contract."""
from __future__ import annotations

import json
import ipaddress
import ssl
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from content.release.model import DeploymentEnvironment


_API_REQUEST_TIMEOUT_SECONDS = active_runtime_policy().api_request_timeout_seconds


class GammaHomepageApiVerificationError(ValueError):
    """A Gamma API response does not prove the imported homepage is consumable."""


@dataclass(frozen=True)
class GammaHomepageApiCase:
    entity_ref: str
    homepage_id: str
    title: str


def _read_cases(path: Path, *, release_id: str) -> list[GammaHomepageApiCase]:
    try:
        payload = read_json(path)
        assert_valid(payload, "release", "gamma_app_uat_case_manifest", label="gamma_app_uat_case_manifest")
    except (OSError, TypeError, ValueError) as exc:
        raise GammaHomepageApiVerificationError(f"Gamma App UAT case manifest is invalid: {exc}") from exc
    if payload.get("releaseId") != release_id:
        raise GammaHomepageApiVerificationError("Gamma App UAT case manifest releaseId mismatch")
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise GammaHomepageApiVerificationError("Gamma App UAT case manifest cases must be an array")
    cases: list[GammaHomepageApiCase] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise GammaHomepageApiVerificationError(f"Gamma App UAT case {index} must be an object")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        title = str(row.get("title") or "").strip()
        if not entity_ref or not homepage_id or not title:
            raise GammaHomepageApiVerificationError(f"Gamma App UAT case {index} has an empty identity")
        cases.append(GammaHomepageApiCase(entity_ref, homepage_id, title))
    if not cases or len({case.entity_ref for case in cases}) != len(cases):
        raise GammaHomepageApiVerificationError("Gamma App UAT case identities are incomplete or duplicated")
    return cases


@contextmanager
def _temporary_host_resolution(url: str, resolve_host: str):
    """Resolve one local-environment URL to an explicit IP without changing URL identity."""
    expected_host = urlparse(url).hostname or ""
    if not resolve_host or not expected_host:
        yield
        return
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == expected_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _api_object(url: str, *, insecure_tls: bool, resolve_host: str) -> tuple[int, Mapping[str, Any]]:
    context = ssl._create_unverified_context() if insecure_tls else None  # noqa: SLF001
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Client-Page-Id": "entity.homepage.introduction",
        },
        method="GET",
    )
    try:
        handlers = [ProxyHandler({})]
        if context is not None:
            handlers.append(HTTPSHandler(context=context))
        opener = build_opener(*handlers)
        with _temporary_host_resolution(url, resolve_host):
            with opener.open(
                request,
                timeout=_API_REQUEST_TIMEOUT_SECONDS,
            ) as response:  # noqa: S310
                status = int(response.status)
                payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GammaHomepageApiVerificationError(f"GET {url} returned HTTP {exc.code}") from exc
    except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GammaHomepageApiVerificationError(f"GET {url} failed: {exc}") from exc
    if status != HTTPStatus.OK or not isinstance(payload, Mapping):
        raise GammaHomepageApiVerificationError(f"GET {url} returned an invalid JSON object")
    return status, payload


def _required_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GammaHomepageApiVerificationError(f"{endpoint} lacks required {field}")
    return value.strip()


def _verify_case(
    api_base_url: str,
    case: GammaHomepageApiCase,
    *,
    insecure_tls: bool,
    resolve_host: str,
) -> dict[str, Any]:
    base = api_base_url.rstrip("/")
    homepage_id = quote(case.homepage_id, safe="")
    detail_status, detail = _api_object(
        f"{base}/v1/homepages/{homepage_id}",
        insecure_tls=insecure_tls,
        resolve_host=resolve_host,
    )
    introduction_status, introduction = _api_object(
        f"{base}/v1/homepages/{homepage_id}/introduction",
        insecure_tls=insecure_tls,
        resolve_host=resolve_host,
    )
    if _required_text(detail, "_id", endpoint="homepage detail") != case.homepage_id:
        raise GammaHomepageApiVerificationError(f"homepage detail id mismatch for {case.entity_ref}")
    if _required_text(detail, "title", endpoint="homepage detail") != case.title:
        raise GammaHomepageApiVerificationError(f"homepage detail title mismatch for {case.entity_ref}")
    cover_url = _required_text(detail, "coverUrl", endpoint="homepage detail")
    if _required_text(introduction, "homepageId", endpoint="homepage introduction") != case.homepage_id:
        raise GammaHomepageApiVerificationError(f"homepage introduction id mismatch for {case.entity_ref}")
    if _required_text(introduction, "displayName", endpoint="homepage introduction") != case.title:
        raise GammaHomepageApiVerificationError(f"homepage introduction title mismatch for {case.entity_ref}")
    if _required_text(introduction, "coverUrl", endpoint="homepage introduction") != cover_url:
        raise GammaHomepageApiVerificationError(f"homepage cover mismatch between detail and introduction for {case.entity_ref}")
    sections = introduction.get("sections")
    if not isinstance(sections, list) or not sections:
        raise GammaHomepageApiVerificationError(f"homepage introduction has no sections for {case.entity_ref}")
    return {
        "entityRef": case.entity_ref,
        "homepageId": case.homepage_id,
        "title": case.title,
        "detailStatus": detail_status,
        "introductionStatus": introduction_status,
        "coverUrl": cover_url,
        "sectionCount": len(sections),
    }


def write_gamma_homepage_api_verification(
    *,
    release_id: str,
    run_id: str,
    case_manifest_path: Path,
    output_path: Path,
    api_base_url: str,
    insecure_tls: bool,
    resolve_host: str = "",
) -> Path:
    """Call the Gamma homepage APIs and write a schema-validated evidence report."""
    if not api_base_url.startswith(("http://", "https://")):
        raise GammaHomepageApiVerificationError("Gamma homepage API base URL must be http(s)")
    resolve_host = resolve_host.strip()
    if resolve_host:
        try:
            ipaddress.ip_address(resolve_host)
        except ValueError as exc:
            raise GammaHomepageApiVerificationError("Gamma API resolve host must be an IP address") from exc
    cases = _read_cases(case_manifest_path, release_id=release_id)
    try:
        case_ref = case_manifest_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise GammaHomepageApiVerificationError("Gamma App UAT case manifest must be below QWQ_OUTPUT_ROOT") from exc
    entities = [
        _verify_case(
            api_base_url,
            case,
            insecure_tls=insecure_tls,
            resolve_host=resolve_host,
        )
        for case in cases
    ]
    payload = {
        "schemaVersion": "quwoquan_data.gamma_homepage_api_verification/1",
        "environment": DeploymentEnvironment.GAMMA,
        "releaseId": release_id,
        "runId": run_id,
        "sourceUatCasesRef": case_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "entities": entities,
        "issues": [],
    }
    if resolve_host:
        payload["apiResolveHost"] = resolve_host
    try:
        assert_valid(payload, "release", "gamma_homepage_api_verification", label="gamma_homepage_api_verification")
    except (TypeError, ValueError) as exc:
        raise GammaHomepageApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise GammaHomepageApiVerificationError(f"Gamma homepage API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = [
    "GammaHomepageApiVerificationError",
    "write_gamma_homepage_api_verification",
]

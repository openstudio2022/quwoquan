"""Network IO for public-source research providers."""
from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import urllib.parse
from typing import Any

from core.runtime_policy import active_runtime_policy
from content.source.research import network_breaker


_USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
_HTTP_METADATA_MARKER = b"\n__QWQ_HTTP_META__"
_HTTP_METADATA_FORMAT = "\n__QWQ_HTTP_META__%{http_code}\t%{url_effective}"


@dataclass(frozen=True, slots=True)
class HttpFetchResult:
    returncode: int
    status_code: int
    final_url: str
    body: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and 200 <= self.status_code < 300


def fetch_http(url: str, *, timeout: int) -> HttpFetchResult:
    if network_breaker.BREAKER.is_open(url) or network_breaker.wave_budget_exceeded():
        return HttpFetchResult(returncode=-1, status_code=0, final_url="", body=b"")
    effective_timeout = max(1, int(timeout))
    policy = active_runtime_policy()
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-L",
            "-A",
            _USER_AGENT,
            "--retry",
            str(max(1, int(policy.curl_retries))),
            "--retry-delay",
            str(policy.curl_retry_delay_seconds),
            "--retry-all-errors",
            "--max-time",
            str(effective_timeout),
            "--write-out",
            _HTTP_METADATA_FORMAT,
            url,
        ],
        capture_output=True,
        check=False,
    )
    stdout = (
        proc.stdout
        if isinstance(proc.stdout, bytes)
        else bytes(str(proc.stdout or ""), "utf-8")
    )
    body, marker, metadata = stdout.rpartition(_HTTP_METADATA_MARKER)
    status_code = 0
    final_url = ""
    if marker:
        status_text, separator, final_url_bytes = metadata.partition(b"\t")
        if separator:
            try:
                status_code = int(status_text.decode("ascii"))
            except ValueError:
                status_code = 0
            final_url = final_url_bytes.decode("utf-8", errors="replace").strip()
    if proc.returncode == 0:
        network_breaker.BREAKER.record_success(url)
    elif proc.returncode in network_breaker.NETWORK_CURL_EXIT_CODES:
        network_breaker.BREAKER.record_network_failure(url)
    return HttpFetchResult(
        returncode=int(proc.returncode),
        status_code=status_code,
        final_url=final_url,
        body=body if marker else stdout,
    )


def curl_json(url: str, *, timeout: int) -> dict[str, Any]:
    response = fetch_http(url, timeout=timeout)
    if not response.ok:
        return {}
    try:
        data = json.loads(response.body.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def post_form_json(
    url: str,
    *,
    fields: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    """POST form fields once and decode JSON; the source adapter owns retries."""
    if network_breaker.BREAKER.is_open(url) or network_breaker.wave_budget_exceeded():
        return {}
    policy = active_runtime_policy()
    command = [
        "curl",
        "-sS",
        "-L",
        "-f",
        "-A",
        _USER_AGENT,
        "--retry",
        "0",
        "--retry-delay",
        str(policy.curl_retry_delay_seconds),
        "--retry-all-errors",
        "--max-time",
        str(max(1, int(timeout))),
    ]
    for key, value in fields.items():
        command.extend(["--data-urlencode", f"{key}={value}"])
    command.append(url)
    proc = subprocess.run(command, capture_output=True, check=False)
    if proc.returncode == 0:
        network_breaker.BREAKER.record_success(url)
    elif proc.returncode in network_breaker.NETWORK_CURL_EXIT_CODES:
        network_breaker.BREAKER.record_network_failure(url)
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def curl_text(url: str, *, timeout: int) -> str:
    response = fetch_http(url, timeout=timeout)
    if not response.ok:
        return ""
    return response.body.decode("utf-8", errors="replace")


def wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return curl_json(
        f"https://{host}/w/api.php?{query}",
        timeout=active_runtime_policy().provider_timeouts.mediawiki_seconds,
    )

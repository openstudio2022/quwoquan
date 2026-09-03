"""Network IO for public-source research providers."""
from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import urllib.parse
from typing import Any

from core.rate_limit import shared_rate_limiter


USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@example.org)"
_HTTP_METADATA_MARKER = b"\n__QWQ_HTTP_META__"
_HTTP_METADATA_FORMAT = "\n__QWQ_HTTP_META__%{http_code}\t%{url_effective}"
_MEDIAWIKI_LIMITER_ID = "mediawiki_api"
_CURL_RETRIES = 1
_CURL_RETRY_DELAY_SECONDS = 1
_MEDIAWIKI_TIMEOUT_SECONDS = 20
_MEDIAWIKI_INTER_REQUEST_DELAY_SECONDS = 0.3


class NetworkFetchError(RuntimeError):
    """An outbound request did not complete, so there is no result to return.

    Decoding helpers collapse a rich `HttpFetchResult` into a plain dict or str,
    which leaves failure with nowhere to live. Returning an empty value there
    would make "the host refused us" indistinguishable from "the host says there
    is nothing", and a caller cannot retry or report what it cannot see. Failure
    is raised so it stays a distinct state from present-but-empty.
    """

    def __init__(
        self,
        url: str,
        *,
        status_code: int,
        returncode: int,
        reason: str,
    ) -> None:
        super().__init__(
            f"outbound fetch did not complete: {reason} "
            f"(status={status_code}, curl={returncode}, url={url[:240]})"
        )
        self.url = url
        self.status_code = status_code
        self.returncode = returncode
        self.reason = reason


@dataclass(frozen=True, slots=True)
class HttpFetchResult:
    returncode: int
    status_code: int
    final_url: str
    body: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and 200 <= self.status_code < 300


def fetch_http(
    url: str,
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> HttpFetchResult:
    effective_timeout = max(1, int(timeout))
    header_arguments: list[str] = []
    for name, value in (headers or {}).items():
        header_arguments.extend(["-H", f"{name}: {value}"])
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-L",
            "-A",
            USER_AGENT,
            *header_arguments,
            "--retry",
            str(_CURL_RETRIES),
            "--retry-delay",
            str(_CURL_RETRY_DELAY_SECONDS),
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
    return HttpFetchResult(
        returncode=int(proc.returncode),
        status_code=status_code,
        final_url=final_url,
        body=body if marker else stdout,
    )


def curl_json(url: str, *, timeout: int) -> dict[str, Any]:
    """Fetch and decode one JSON object; an empty object means the host said so."""
    response = fetch_http(url, timeout=timeout)
    if not response.ok:
        raise NetworkFetchError(
            url,
            status_code=response.status_code,
            returncode=response.returncode,
            reason="transport or status failure",
        )
    try:
        data = json.loads(response.body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise NetworkFetchError(
            url,
            status_code=response.status_code,
            returncode=response.returncode,
            reason="response body is not JSON",
        ) from exc
    if not isinstance(data, dict):
        raise NetworkFetchError(
            url,
            status_code=response.status_code,
            returncode=response.returncode,
            reason=f"response JSON is {type(data).__name__}, not an object",
        )
    return data


def post_form_json(
    url: str,
    *,
    fields: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    """POST form fields once and decode JSON; the source adapter owns retries."""
    command = [
        "curl",
        "-sS",
        "-L",
        "-f",
        "-A",
        USER_AGENT,
        "--retry",
        "0",
        "--retry-delay",
        str(_CURL_RETRY_DELAY_SECONDS),
        "--retry-all-errors",
        "--max-time",
        str(max(1, int(timeout))),
    ]
    for key, value in fields.items():
        command.extend(["--data-urlencode", f"{key}={value}"])
    command.append(url)
    proc = subprocess.run(command, capture_output=True, check=False)
    if proc.returncode != 0:
        raise NetworkFetchError(
            url,
            status_code=0,
            returncode=int(proc.returncode),
            reason="transport failure",
        )
    try:
        payload = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise NetworkFetchError(
            url,
            status_code=0,
            returncode=int(proc.returncode),
            reason="response body is not JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise NetworkFetchError(
            url,
            status_code=0,
            returncode=int(proc.returncode),
            reason=f"response JSON is {type(payload).__name__}, not an object",
        )
    return payload


def curl_text(url: str, *, timeout: int) -> str:
    """Fetch one document as text; an empty string means the host served nothing."""
    response = fetch_http(url, timeout=timeout)
    if not response.ok:
        raise NetworkFetchError(
            url,
            status_code=response.status_code,
            returncode=response.returncode,
            reason="transport or status failure",
        )
    return response.body.decode("utf-8", errors="replace")


def wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    """Call one MediaWiki API host under the pacing that host is owed.

    Every research provider reaches MediaWiki through here, so this is where the
    interval belongs: paced per host and shared process-wide, the callers cannot
    add up into a burst no single one of them intended.
    """
    query = urllib.parse.urlencode(params)
    shared_rate_limiter(
        _MEDIAWIKI_LIMITER_ID,
        f"https://{host}",
        max_requests_per_second=0.0,
        crawl_delay=_MEDIAWIKI_INTER_REQUEST_DELAY_SECONDS,
    ).wait()
    return curl_json(
        f"https://{host}/w/api.php?{query}",
        timeout=_MEDIAWIKI_TIMEOUT_SECONDS,
    )

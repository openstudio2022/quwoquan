"""Govern synthetic-DNS network-extension admission for HTTPS image transport."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import ssl
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.schema import assert_valid

NETWORK_ADMISSION_PATH = (
    CONTROL_PLANE_SHARED_ROOT / "catalogs" / "professional_image_network_admission.yaml"
)


def _load_admission(path: Path = NETWORK_ADMISSION_PATH) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"professional image network admission is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError("professional image network admission must be an object")
    assert_valid(
        value,
        "source",
        "professional_image_network_admission",
        label="professional image network admission",
    )
    return value


def _host_allowed(host: str, policy: Mapping[str, Any]) -> bool:
    exact = {str(value).casefold() for value in policy["allowedExactHosts"]}
    suffixes = tuple(str(value).casefold() for value in policy["allowedHostSuffixes"])
    return host in exact or any(host.endswith("." + suffix) for suffix in suffixes)


def resolve_https_admission(url: str) -> dict[str, Any]:
    """Classify public DNS or an explicitly governed synthetic-DNS TLS route."""
    parsed = urllib.parse.urlparse(url)
    host = str(parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise ValueError("professional image HTTPS host is missing")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("professional image network extension forbids literal IP URLs")
    try:
        addresses = sorted({
            result[4][0]
            for result in socket.getaddrinfo(
                host, parsed.port or 443, type=socket.SOCK_STREAM
            )
        })
    except socket.gaierror as exc:
        raise ValueError("professional image host DNS resolution failed") from exc
    if not addresses:
        raise ValueError("professional image host DNS resolution is empty")
    parsed_addresses = tuple(ipaddress.ip_address(value) for value in addresses)
    public = all(value.is_global for value in parsed_addresses)
    if public:
        return {
            "admissionRevision": _load_admission()["revision"],
            "admissionMode": "public_dns",
            "host": host,
            "resolvedAddresses": addresses,
        }
    policy = _load_admission()
    synthetic_networks = tuple(
        ipaddress.ip_network(str(value)) for value in policy["syntheticDnsCidrs"]
    )
    synthetic = all(
        any(address in network for network in synthetic_networks)
        for address in parsed_addresses
    )
    if not synthetic or not _host_allowed(host, policy):
        raise ValueError("professional image host resolves to a non-public address")
    return {
        "admissionRevision": str(policy["revision"]),
        "admissionMode": "managed_network_extension",
        "host": host,
        "resolvedAddresses": addresses,
    }


def verified_tls_context() -> ssl.SSLContext:
    """Return the only TLS context used by professional-image network admission."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def https_tls_peer(
    response: Any,
    *,
    requested_url: str,
    final_url: str,
    admission: Mapping[str, Any],
) -> dict[str, Any]:
    """Capture verified peer state before response-body EOF releases the socket."""
    final_host = str(urllib.parse.urlparse(final_url).hostname or "").casefold()
    request_host = str(urllib.parse.urlparse(requested_url).hostname or "").casefold()
    raw = getattr(getattr(response, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    if not isinstance(sock, ssl.SSLSocket):
        raise ValueError("professional image HTTPS response lacks a TLS peer socket")
    context = sock.context
    server_hostname = str(sock.server_hostname or "").casefold()
    certificate = sock.getpeercert(binary_form=True)
    cipher = sock.cipher()
    peer = str(sock.getpeername()[0])
    if (
        context.verify_mode != ssl.CERT_REQUIRED
        or context.check_hostname is not True
        or server_hostname != final_host
        or peer not in admission["resolvedAddresses"]
        or not certificate
        or not cipher
    ):
        raise ValueError("professional image TLS hostname/peer provenance drift")
    return {
        "admissionRevision": str(admission["admissionRevision"]),
        "admissionMode": str(admission["admissionMode"]),
        "requestedUrl": requested_url,
        "finalUrl": final_url,
        "requestHost": request_host,
        "finalHost": final_host,
        "resolvedAddresses": list(admission["resolvedAddresses"]),
        "peerAddress": peer,
        "tls": {
            "serverHostname": server_hostname,
            "version": str(sock.version()),
            "cipher": str(cipher[0]),
            "peerCertificateSha256": "sha256:" + hashlib.sha256(certificate).hexdigest(),
            "systemTrustVerified": True,
            "hostnameVerified": True,
        },
        "httpStatus": int(getattr(response, "status", 0)),
    }


def https_transport_evidence(
    peer: Mapping[str, Any],
    *,
    content_type: str,
    body: bytes,
) -> dict[str, Any]:
    """Bind captured TLS peer provenance to the exact returned bytes."""
    evidence = {
        "schema": "quwoquan_data.professional_image_https_transport_evidence",
        **dict(peer),
        "contentType": content_type,
        "responseBytes": len(body),
        "responseSha256": "sha256:" + hashlib.sha256(body).hexdigest(),
    }
    assert_valid(
        evidence,
        "source",
        "professional_image_https_transport_evidence",
        label="professional image HTTPS transport evidence",
    )
    return evidence


__all__ = [
    "NETWORK_ADMISSION_PATH",
    "https_tls_peer",
    "https_transport_evidence",
    "resolve_https_admission",
    "verified_tls_context",
]

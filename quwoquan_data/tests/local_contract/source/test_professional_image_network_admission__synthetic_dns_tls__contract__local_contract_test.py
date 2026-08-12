from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from content.source import professional_image_network_admission as admission


def _policy() -> dict:
    return {
        "schema": "quwoquan_data.professional_image_network_admission",
        "revision": "professional-image-network-admission-v1",
        "syntheticDnsCidrs": ["198.18.0.0/15"],
        "allowedExactHosts": ["api.openverse.org"],
        "allowedHostSuffixes": [],
        "tls": {
            "minimumVersion": "TLSv1.2",
            "systemTrustRequired": True,
            "hostnameVerificationRequired": True,
        },
    }


def test_synthetic_dns_requires_allowlisted_hostname_not_literal_ip_or_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admission, "_load_admission", _policy)
    monkeypatch.setattr(
        admission.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("198.18.1.115", 443))],
    )
    accepted = admission.resolve_https_admission(
        "https://api.openverse.org/v1/images/?q=test"
    )
    assert accepted == {
        "admissionRevision": "professional-image-network-admission-v1",
        "admissionMode": "managed_network_extension",
        "host": "api.openverse.org",
        "resolvedAddresses": ["198.18.1.115"],
    }
    with pytest.raises(ValueError, match="literal IP"):
        admission.resolve_https_admission("https://198.18.1.115/v1/images/")
    with pytest.raises(ValueError, match="non-public"):
        admission.resolve_https_admission("https://attacker.example/v1/images/")

    monkeypatch.setattr(
        admission.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="non-public"):
        admission.resolve_https_admission("https://api.openverse.org/v1/images/")


def test_transport_evidence_binds_sni_peer_certificate_and_response_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"results":[]}'

    class FakeTlsSocket:
        context = SimpleNamespace(verify_mode=admission.ssl.CERT_REQUIRED, check_hostname=True)
        server_hostname = "api.openverse.org"

        @staticmethod
        def getpeercert(*, binary_form: bool = False):
            return b"certificate" if binary_form else {}

        @staticmethod
        def cipher():
            return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        @staticmethod
        def getpeername():
            return ("198.18.1.115", 443)

        @staticmethod
        def version():
            return "TLSv1.3"

    monkeypatch.setattr(admission.ssl, "SSLSocket", FakeTlsSocket)
    response = SimpleNamespace(
        fp=SimpleNamespace(raw=SimpleNamespace(_sock=FakeTlsSocket())),
        status=200,
    )
    peer = admission.https_tls_peer(
        response,
        requested_url="https://api.openverse.org/v1/images/?q=test",
        final_url="https://api.openverse.org/v1/images/?q=test",
        admission={
            "admissionRevision": "professional-image-network-admission-v1",
            "admissionMode": "managed_network_extension",
            "host": "api.openverse.org",
            "resolvedAddresses": ["198.18.1.115"],
        },
    )
    evidence = admission.https_transport_evidence(
        peer, content_type="application/json", body=body
    )
    assert evidence["tls"]["serverHostname"] == "api.openverse.org"
    assert evidence["peerAddress"] == "198.18.1.115"
    assert evidence["responseSha256"] == (
        "sha256:" + hashlib.sha256(body).hexdigest()
    )

    response.fp.raw._sock.server_hostname = "attacker.example"
    with pytest.raises(ValueError, match="hostname/peer provenance drift"):
        admission.https_tls_peer(
            response,
            requested_url="https://api.openverse.org/v1/images/?q=test",
            final_url="https://api.openverse.org/v1/images/?q=test",
            admission={
                "admissionRevision": "professional-image-network-admission-v1",
                "admissionMode": "managed_network_extension",
                "host": "api.openverse.org",
                "resolvedAddresses": ["198.18.1.115"],
            },
        )

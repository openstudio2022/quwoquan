"""research isolation runtime probe 的组装、fail-closed 与 create-once 契约。

HTTP 层全部通过 monkeypatch 模块级 request/fetch 函数替换；schema 断言直接读
``quwoquan_data/schema/release/research_isolation_verification.schema.json``
做结构判定，不 import quwoquan_data 代码。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import research_isolation_runtime_probe as probe
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
)

SCHEMA_PATH = (
    ROOT / "quwoquan_data/schema/release/research_isolation_verification.schema.json"
)

RELEASE_ID = "rel-research-0001"
VERIFY_RUN_ID = "verify-run-0001"
MANIFEST_DIGEST = "sha256:" + "a" * 64
POLICY_SHA256 = "sha256:" + "b" * 64
SUBJECT_HASH = "sha256:" + hashlib.sha256(b"research-subject").hexdigest()
ATTESTATION_TOKEN = "djEuc2hh.attestation-token"
ATTESTATION_ID_HASH = (
    "sha256:" + hashlib.sha256(ATTESTATION_TOKEN.encode("utf-8")).hexdigest()
)
API_BASE = "https://api.alpha.quwoquan.com:18443"
MEDIA_BASE = "https://cdn.alpha.quwoquan.com:18444/media/image"
ASSET_ID = "asset-0001"
POST_ID = "post-0001"
AUDIT_ID = "audit-0001"
ORIGINAL_PATH = f"/media/image/original/{ASSET_ID}"
ORIGINAL_SIGN = "d" * 64
ORIGINAL_EXPIRY = "1767226200"
ORIGINAL_URL = (
    f"https://cdn.alpha.quwoquan.com:18444{ORIGINAL_PATH}"
    f"?sign={ORIGINAL_SIGN}&t={ORIGINAL_EXPIRY}"
)
UNSIGNED_ORIGINAL_URL = f"https://cdn.alpha.quwoquan.com:18444{ORIGINAL_PATH}"
FORGED_SIGNATURE_URL = (
    f"https://cdn.alpha.quwoquan.com:18444{ORIGINAL_PATH}"
    f"?sign={'0' * 64}&t={ORIGINAL_EXPIRY}"
)
TAMPERED_EXPIRY_URL = (
    f"https://cdn.alpha.quwoquan.com:18444{ORIGINAL_PATH}"
    f"?sign={ORIGINAL_SIGN}&t={int(ORIGINAL_EXPIRY) + 1}"
)
ANONYMOUS_MEDIA_URL = f"{MEDIA_BASE}/{ASSET_ID}"


def _readback_view() -> dict[str, object]:
    return {
        "releaseId": RELEASE_ID,
        "manifestDigest": MANIFEST_DIGEST,
        "subjectHash": SUBJECT_HASH,
        "attestationIdHash": ATTESTATION_ID_HASH,
        "signatureVerified": True,
        "researchBadgeVisible": True,
        "postIds": [POST_ID, "post-0002"],
        "entityRefs": ["entity-0001"],
        "mediaAssetIds": [ASSET_ID, "asset-0002"],
        "publicCdnDetected": False,
        "anonymousMediaUrlDetected": False,
    }


class FakeResearchEnvironment:
    """一个内存中的本地环境替身；每个探针路径都必须被显式声明。"""

    def __init__(
        self,
        *,
        share_status: int = 403,
        anonymous_content_status: int = 401,
        anonymous_media_status: int = 403,
        unsigned_original_status: int = 403,
        signed_access_status: int = 200,
        range_access_status: int = 206,
        forged_signature_status: int = 403,
        tampered_expiry_status: int = 403,
        readback_view: dict[str, object] | None = None,
        ttl_seconds: int = 600,
    ) -> None:
        self.share_status = share_status
        self.anonymous_content_status = anonymous_content_status
        self.anonymous_media_status = anonymous_media_status
        self.unsigned_original_status = unsigned_original_status
        self.signed_access_status = signed_access_status
        self.range_access_status = range_access_status
        self.forged_signature_status = forged_signature_status
        self.tampered_expiry_status = tampered_expiry_status
        self.readback_view = readback_view or _readback_view()
        self.ttl_seconds = ttl_seconds
        self.request_header_log: list[dict[str, str]] = []

    def request_json(
        self,
        base_url: str,
        *,
        path: str,
        session: LocalAcceptanceSession,
        method: str = "GET",
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 12.0,
    ) -> dict[str, object]:
        assert base_url == API_BASE
        assert isinstance(session, LocalAcceptanceSession)
        headers = dict(headers or {})
        self.request_header_log.append(headers)
        assert headers.get("X-Request-Id") and headers.get("X-Trace-Id")
        if method == "POST" and path == "/auth/research/session":
            return {
                "subjectHash": SUBJECT_HASH,
                "attestationId": ATTESTATION_TOKEN,
                "expiresAt": "2026-08-13T00:15:00+00:00",
            }
        if method == "GET" and path == "/auth/research/session/attestation":
            assert headers.get("X-Research-Identity-Attestation") == ATTESTATION_TOKEN
            return {
                "subjectHash": SUBJECT_HASH,
                "attestationId": ATTESTATION_TOKEN,
                "expiresAt": "2026-08-13T00:15:00+00:00",
            }
        if method == "GET" and path == "/content/research/readback":
            assert headers.get("X-Research-Identity-Attestation") == ATTESTATION_TOKEN
            return dict(self.readback_view)
        if method == "POST" and path == f"/content/media/{ASSET_ID}/original:access":
            assert headers.get("Idempotency-Key")
            assert body == {"mediaId": ASSET_ID, "purpose": "view"}
            return {
                "mediaId": ASSET_ID,
                "status": "granted",
                "originalUrl": ORIGINAL_URL,
                "format": "jpeg",
                "sizeBytes": 12345,
                "expiresAt": "2026-08-13T00:10:00+00:00",
                "ttlSeconds": self.ttl_seconds,
                "auditId": AUDIT_ID,
            }
        if method == "GET" and path == (
            f"/content/media/original-access-audits/{AUDIT_ID}"
        ):
            return {"auditId": AUDIT_ID, "mediaId": ASSET_ID, "purpose": "view"}
        if method == "POST" and path == f"/content/posts/{POST_ID}/outbound-shares":
            assert headers.get("Idempotency-Key")
            if self.share_status in {401, 403}:
                raise LocalEnvironmentHTTPError(
                    method=method,
                    path=path,
                    status=self.share_status,
                )
            return {"eventId": "evt-0001", "postId": POST_ID, "replayed": False}
        raise AssertionError(f"unexpected authenticated call {method} {path}")

    def request_public_json(
        self,
        base_url: str,
        *,
        path: str,
        method: str = "GET",
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 12.0,
    ) -> dict[str, object]:
        assert base_url == API_BASE
        headers = dict(headers or {})
        assert "Authorization" not in headers
        assert "X-Research-Identity-Attestation" not in headers
        if method == "GET" and path == "/content/research/readback":
            if self.anonymous_content_status in {401, 403}:
                raise LocalEnvironmentHTTPError(
                    method=method,
                    path=path,
                    status=self.anonymous_content_status,
                )
            return dict(self.readback_view)
        raise AssertionError(f"unexpected anonymous call {method} {path}")

    def fetch_media_status(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 12.0,
    ) -> int:
        headers = dict(headers or {})
        assert headers.get("X-Request-Id") and headers.get("X-Trace-Id")
        if url == ANONYMOUS_MEDIA_URL:
            return self.anonymous_media_status
        if url == UNSIGNED_ORIGINAL_URL:
            return self.unsigned_original_status
        if url == FORGED_SIGNATURE_URL:
            return self.forged_signature_status
        if url == TAMPERED_EXPIRY_URL:
            return self.tampered_expiry_status
        if url == ORIGINAL_URL:
            if headers.get("Range") == "bytes=0-1":
                return self.range_access_status
            return self.signed_access_status
        raise AssertionError(f"unexpected media fetch {url}")


def _fake_actor() -> SimpleNamespace:
    return SimpleNamespace(
        session=LocalAcceptanceSession(
            owner_id="uo_01_ph_0000_research",
            persona_id="persona-research",
            access_token="ephemeral-local-bearer",
        )
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: FakeResearchEnvironment,
) -> Path:
    """接管 probe 的全部环境边界并返回 QWQ 输出根。"""

    output_root = tmp_path / "qwq-output"
    opened: list[dict[str, object]] = []

    def fake_open_session(base_url: str, **kwargs: object) -> SimpleNamespace:
        assert base_url == API_BASE
        assert kwargs["identity_set_id"] == "research-identity"
        assert kwargs["actor_index"] == 0
        opened.append(dict(kwargs))
        return _fake_actor()

    monkeypatch.setattr(probe, "request_local_environment_json", environment.request_json)
    monkeypatch.setattr(
        probe,
        "request_local_environment_public_json",
        environment.request_public_json,
    )
    monkeypatch.setattr(probe, "fetch_media_status", environment.fetch_media_status)
    monkeypatch.setattr(
        probe,
        "_policy_snapshot",
        lambda _environment: (POLICY_SHA256, 900),
    )
    monkeypatch.setattr(probe, "load_environment_topology", lambda: {"targets": {}})
    monkeypatch.setattr(
        probe,
        "get_target",
        lambda _topology, _target: {
            "publicBases": {"api": API_BASE, "mediaImage": MEDIA_BASE}
        },
    )
    monkeypatch.setattr(
        probe,
        "root_certificate_path",
        lambda _target: tmp_path / "root-ca.pem",
    )
    monkeypatch.setattr(probe, "open_local_phone_acceptance_session", fake_open_session)
    monkeypatch.setattr(probe, "output_root", lambda: output_root)
    return output_root


def _run() -> dict[str, object]:
    return probe.run_research_isolation_runtime_probe(
        environment="alpha",
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        manifest_digest=MANIFEST_DIGEST,
    )


def _proof_path(output_root: Path) -> Path:
    return (
        output_root
        / "env"
        / "alpha"
        / "runs"
        / "data-release"
        / RELEASE_ID
        / VERIFY_RUN_ID
        / "research-isolation-runtime-proof.json"
    )


def _document_checksum(document: dict[str, object]) -> str:
    unsigned = dict(document)
    unsigned.pop("verificationChecksum", None)
    return "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _all_operations(document: dict[str, object]) -> list[dict[str, object]]:
    denied = document["deniedCapabilities"]
    signed = document["signedMedia"]
    return [
        document["identityIssuance"]["operation"],
        document["identityAttestation"]["operation"],
        document["internalAppReadback"]["operation"],
        document["anonymousContentProbe"]["operation"],
        document["anonymousMediaProbe"]["operation"],
        document["networkExposureReadback"]["operation"],
        denied["share"]["operation"],
        denied["export"]["operation"],
        signed["issuanceOperation"],
        signed["accessOperation"],
        signed["rangeAccessOperation"],
        signed["forgedSignatureOperation"],
        signed["tamperedExpiryOperation"],
        signed["auditReadbackOperation"],
        document["positiveReadback"]["operation"],
    ]


def _assert_document_matches_data_schema(document: dict[str, object]) -> None:
    """按 Data schema JSON 的结构约束逐点断言（不 import quwoquan_data 代码）。"""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert set(document) <= set(schema["properties"])
    for key in schema["required"]:
        assert key in document, f"schema required key missing: {key}"

    assert document["schema"] == schema["properties"]["schema"]["const"]
    assert document["environment"] in schema["properties"]["environment"]["enum"]
    assert document["releaseClass"] == schema["properties"]["releaseClass"]["const"]
    assert (
        document["productLifecycleState"]
        == schema["properties"]["productLifecycleState"]["const"]
    )
    assert document["outcome"] == "PASS"
    assert re.fullmatch(
        schema["properties"]["policyRef"]["pattern"],
        document["policyRef"],
    )

    pass_branch = schema["allOf"][0]["then"]
    for key in pass_branch["required"]:
        assert key in document, f"PASS branch key missing: {key}"
    assert "blocker" not in document

    digest_pattern = re.compile(schema["$defs"]["digest"]["pattern"])
    for label, value in (
        ("manifestDigest", document["manifestDigest"]),
        ("policySha256", document["policySha256"]),
        ("subjectHash", document["subjectHash"]),
        ("verificationChecksum", document["verificationChecksum"]),
        ("identityIssuance.attestationIdHash", document["identityIssuance"]["attestationIdHash"]),
        ("identityAttestation.attestationIdHash", document["identityAttestation"]["attestationIdHash"]),
        ("internalAppReadback.attestationIdHash", document["internalAppReadback"]["attestationIdHash"]),
        ("signedMedia.signedUrlHash", document["signedMedia"]["signedUrlHash"]),
    ):
        assert digest_pattern.fullmatch(str(value)), f"{label} is not a digest"

    identity_required = set(schema["$defs"]["identityProof"]["required"])
    for segment in ("identityIssuance", "identityAttestation"):
        assert set(document[segment]) == identity_required
        assert re.fullmatch(
            schema["$defs"]["repositoryRef"]["pattern"],
            document[segment]["contractRef"],
        )

    operation_required = set(schema["$defs"]["operation"]["required"])
    operation_properties = set(schema["$defs"]["operation"]["properties"])
    assert operation_required == operation_properties
    for operation in _all_operations(document):
        assert set(operation) == operation_required
        assert str(operation["path"]).startswith("/")
        assert isinstance(operation["status"], int)
        assert 100 <= operation["status"] <= 599
        assert isinstance(operation["durationMs"], int)
        assert operation["durationMs"] >= 0
        for field in ("pageId", "requestId", "traceId", "startedAt", "endedAt"):
            assert str(operation[field]).strip()

    denied_statuses = set(
        schema["$defs"]["deniedProbe"]["properties"]["operation"]["allOf"][1][
            "properties"
        ]["status"]["enum"]
    )
    for segment in ("anonymousContentProbe", "anonymousMediaProbe"):
        assert document[segment]["decision"] == "denied"
        assert document[segment]["operation"]["status"] in denied_statuses

    capability_statuses = set(
        schema["$defs"]["deniedCapability"]["properties"]["operation"]["allOf"][1][
            "properties"
        ]["status"]["enum"]
    )
    assert set(document["deniedCapabilities"]) == {"share", "export"}
    for row in document["deniedCapabilities"].values():
        assert row["decision"] == "denied"
        assert row["operation"]["status"] in capability_statuses

    success_status = schema["$defs"]["successOperation"]["allOf"][1]["properties"][
        "status"
    ]["const"]
    for operation in (
        document["identityIssuance"]["operation"],
        document["identityAttestation"]["operation"],
        document["internalAppReadback"]["operation"],
        document["networkExposureReadback"]["operation"],
        document["signedMedia"]["issuanceOperation"],
        document["signedMedia"]["auditReadbackOperation"],
        document["positiveReadback"]["operation"],
    ):
        assert operation["status"] == success_status
    access_statuses = set(
        schema["properties"]["signedMedia"]["properties"]["accessOperation"][
            "allOf"
        ][1]["properties"]["status"]["enum"]
    )
    assert document["signedMedia"]["accessOperation"]["status"] in access_statuses

    signed_schema = schema["properties"]["signedMedia"]
    assert set(document["signedMedia"]) == set(signed_schema["required"])
    ttl = document["signedMedia"]["ttlSeconds"]
    assert isinstance(ttl, int)
    assert (
        signed_schema["properties"]["ttlSeconds"]["minimum"]
        <= ttl
        <= signed_schema["properties"]["ttlSeconds"]["maximum"]
    )

    for field in ("entityRefs", "postIds", "mediaAssetIds"):
        rows = document["positiveReadback"][field]
        assert isinstance(rows, list) and rows
        assert all(isinstance(item, str) and item.strip() for item in rows)
        assert len(rows) == len(set(rows))
    assert document["signedMedia"]["assetId"] in document["positiveReadback"][
        "mediaAssetIds"
    ]

    assert document["networkExposureReadback"]["publicCdnDetected"] is False
    assert document["networkExposureReadback"]["anonymousMediaUrlDetected"] is False
    assert document["internalAppReadback"]["signatureVerified"] is True
    assert document["internalAppReadback"]["researchBadgeVisible"] is True


def test_all_green_probes_assemble_a_schema_valid_checksummed_pass_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = _install(monkeypatch, tmp_path, FakeResearchEnvironment())

    result = _run()

    proof_path = _proof_path(output_root)
    assert Path(result["outputPath"]) == proof_path
    assert proof_path.is_file()
    document = json.loads(proof_path.read_text(encoding="utf-8"))

    assert set(document) == set(probe.PASS_DOCUMENT_KEYS)
    assert document["verificationChecksum"] == _document_checksum(document)
    _assert_document_matches_data_schema(document)

    assert document["subjectHash"] == SUBJECT_HASH
    assert (
        document["identityIssuance"]["attestationIdHash"] == ATTESTATION_ID_HASH
    )
    assert (
        document["identityAttestation"]["attestationIdHash"] == ATTESTATION_ID_HASH
    )
    assert document["releaseId"] == RELEASE_ID
    assert document["verifyRunId"] == VERIFY_RUN_ID
    assert document["manifestDigest"] == MANIFEST_DIGEST
    assert document["policySha256"] == POLICY_SHA256
    assert document["policyRef"] == "quwoquan_ops/environments/alpha/runtime.yaml"

    operations = _all_operations(document)
    assert len(operations) == 15
    request_ids = [operation["requestId"] for operation in operations]
    trace_ids = [operation["traceId"] for operation in operations]
    assert len(set(request_ids)) == 15
    assert len(set(trace_ids)) == 15
    page_ids = {operation["pageId"] for operation in operations}
    assert len(page_ids) == 15
    assert all(page.startswith("ops.research_isolation.") for page in page_ids)

    assert result["operationCount"] == 15
    assert result["subjectHash"] == SUBJECT_HASH

    # 边缘复算负例（DEC-031 / OPEN-015 运维加固面）：伪签名与篡改到期
    # 必须以真实私有 key 的 URL 变体被拒绝，Range 段请求逐段复算后放行。
    signed = document["signedMedia"]
    assert signed["forgedSignatureOperation"]["status"] in {401, 403}
    assert signed["tamperedExpiryOperation"]["status"] in {401, 403}
    assert signed["rangeAccessOperation"]["status"] in {200, 206}
    assert signed["forgedSignatureOperation"]["path"] == ORIGINAL_PATH
    assert signed["tamperedExpiryOperation"]["path"] == ORIGINAL_PATH


@pytest.mark.parametrize(
    ("environment_kwargs", "expected_code"),
    (
        ({"share_status": 200}, "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS"),
        (
            {"anonymous_content_status": 200},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"anonymous_media_status": 200},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"unsigned_original_status": 200},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"signed_access_status": 403},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"range_access_status": 403},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"forged_signature_status": 200},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        (
            {"tampered_expiry_status": 200},
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
        ),
        ({"ttl_seconds": 2000}, "OPS.RESEARCH.PROBE_RESPONSE_INVALID"),
        (
            {
                "readback_view": {
                    **_readback_view(),
                    "releaseId": "rel-other",
                }
            },
            "OPS.RESEARCH.PROBE_RESPONSE_INVALID",
        ),
        (
            {
                "readback_view": {
                    **_readback_view(),
                    "signatureVerified": False,
                }
            },
            "OPS.RESEARCH.PROBE_RESPONSE_INVALID",
        ),
    ),
)
def test_any_unexpected_probe_fails_closed_and_writes_no_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment_kwargs: dict[str, object],
    expected_code: str,
) -> None:
    output_root = _install(
        monkeypatch,
        tmp_path,
        FakeResearchEnvironment(**environment_kwargs),
    )

    with pytest.raises(probe.ResearchIsolationProbeError) as excinfo:
        _run()

    assert excinfo.value.code == expected_code
    assert not _proof_path(output_root).exists()
    assert not list(output_root.rglob("research-isolation-runtime-proof.json"))


def test_create_once_conflict_is_rejected_and_existing_bytes_are_kept(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = _install(monkeypatch, tmp_path, FakeResearchEnvironment())

    _run()
    proof_path = _proof_path(output_root)
    original_bytes = proof_path.read_bytes()

    with pytest.raises(probe.ResearchIsolationProbeError) as excinfo:
        _run()

    assert excinfo.value.code == "OPS.RESEARCH.PROOF_ALREADY_EXISTS"
    assert proof_path.read_bytes() == original_bytes

    with pytest.raises(probe.ResearchIsolationProbeError) as write_excinfo:
        probe.write_runtime_proof_create_once(proof_path, {"schema": "x"})
    assert write_excinfo.value.code == "OPS.RESEARCH.PROOF_ALREADY_EXISTS"
    assert proof_path.read_bytes() == original_bytes


def test_duplicate_request_identities_are_rejected_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = _install(monkeypatch, tmp_path, FakeResearchEnvironment())
    monkeypatch.setattr(probe, "new_probe_identity", lambda: "fixed-probe-identity")

    with pytest.raises(probe.ResearchIsolationProbeError) as excinfo:
        _run()

    assert excinfo.value.code == "OPS.RESEARCH.PROOF_EVIDENCE_REUSED"
    assert not _proof_path(output_root).exists()



def _strict_asset(*, kind: str = "image", require_range: bool = False) -> dict[str, object]:
    body = b"\x00\x00\x00\x18ftyp" if kind == "video" else b"private-image"
    return {
        "assetId": "strict-video" if kind == "video" else "strict-image",
        "kind": kind,
        "expectedBytes": len(body),
        "expectedSha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "expectedMimeType": "video/mp4" if kind == "video" else "image/jpeg",
        "privateDeliveryRef": "media/objects/sha256/aa/strict",
        "classifications": ["typed_video", "premium_video"] if kind == "video" else ["image"],
        "requireRange": require_range,
    }


def test_release_bound_signed_media__verifies_full_hash_and_video_range__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _strict_asset(kind="video", require_range=True)
    signed_url = ORIGINAL_URL

    def fake_json(*args, **kwargs):
        assert kwargs["body"] == {"mediaId": "strict-video", "purpose": "view"}
        assert kwargs["headers"]["X-Research-Identity-Attestation"] == ATTESTATION_TOKEN
        return {
            "mediaId": "strict-video",
            "originalUrl": signed_url,
            "auditId": "audit-strict-video",
        }

    calls: list[dict[str, str]] = []

    def fake_bytes(url, *, headers, timeout_seconds, max_bytes):
        calls.append(dict(headers))
        if headers.get("Range") == "bytes=0-1":
            return 206, b"\x00\x00", "video/mp4", "bytes 0-1/12"
        return 200, b"\x00\x00\x00\x18ftyp", "video/mp4", ""

    monkeypatch.setattr(probe, "request_local_environment_json", fake_json)
    monkeypatch.setattr(probe, "_fetch_media_bytes", fake_bytes)

    evidence = probe.probe_release_bound_signed_media(
        api_base_url=API_BASE,
        session=_fake_actor().session,
        asset=asset,
        attestation_token=ATTESTATION_TOKEN,
    )

    assert evidence["hashVerified"] is True
    assert evidence["sha256"] == asset["expectedSha256"]
    assert evidence["rangeStatusCode"] == 206
    assert [call.get("Range") for call in calls] == [None, "bytes=0-1"]


@pytest.mark.parametrize(
    ("failure", "expected_fragment"),
    [
        ("empty", "bytes/MIME/hash"),
        ("hash", "bytes/MIME/hash"),
        ("range", "required byte Range"),
    ],
)
def test_release_bound_signed_media__byte_hash_or_range_failure_gate_blocks__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_fragment: str,
) -> None:
    asset = _strict_asset(kind="video", require_range=True)
    monkeypatch.setattr(
        probe,
        "request_local_environment_json",
        lambda *args, **kwargs: {
            "mediaId": "strict-video",
            "originalUrl": ORIGINAL_URL,
            "auditId": "audit-strict-video",
        },
    )

    def fake_bytes(url, *, headers, timeout_seconds, max_bytes):
        if headers.get("Range") == "bytes=0-1":
            if failure == "range":
                return 200, b"\x00\x00", "video/mp4", ""
            return 206, b"\x00\x00", "video/mp4", "bytes 0-1/12"
        if failure == "empty":
            return 200, b"", "video/mp4", ""
        if failure == "hash":
            return 200, b"wrong-bytes!", "video/mp4", ""
        return 200, b"\x00\x00\x00\x18ftyp", "video/mp4", ""

    monkeypatch.setattr(probe, "_fetch_media_bytes", fake_bytes)

    with pytest.raises(probe.ResearchIsolationProbeError, match=expected_fragment):
        probe.probe_release_bound_signed_media(
            api_base_url=API_BASE,
            session=_fake_actor().session,
            asset=asset,
        )

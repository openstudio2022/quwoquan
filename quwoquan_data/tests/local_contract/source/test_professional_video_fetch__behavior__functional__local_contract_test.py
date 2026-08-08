from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.source import (
    handler_fetch_video,
    professional_video_store,
    professional_video_transport,
)
from content.source.professional_video_receipt import document_digest
from content.source.professional_video_store import write_create_once_video_receipt
from content.source.professional_video_transport import (
    _validated_https_url,
    copy_manual_video,
    redact_sensitive_video_url,
)
from core.io import read_json

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
CLI = DATA_ROOT / "scripts" / "cli.py"


def _run_cli_with_blocked_imageio(*args: str) -> subprocess.CompletedProcess[str]:
    script = """
import builtins
import runpy
import sys

real_import = builtins.__import__
def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "imageio_ffmpeg" or name.startswith("imageio_ffmpeg."):
        raise ModuleNotFoundError(
            "No module named 'imageio_ffmpeg'",
            name="imageio_ffmpeg",
        )
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = blocked_import
cli, *args = sys.argv[1:]
sys.argv = [cli, *args]
runpy.run_path(cli, run_name="__main__")
"""
    return subprocess.run(
        [sys.executable, "-B", "-c", script, str(CLI), *args],
        cwd=DATA_ROOT.parent,
        text=True,
        capture_output=True,
        check=False,
    )


def _candidate() -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    return {
        "sourceId": "pexels_videos",
        "sourceKind": "tourism_video_site",
        "publicationAdmission": "research_release",
        "assetUrl": f"cas://sha256/{'a' * 64}",
        "originalAssetUrl": "https://cdn.example.test/video.mp4",
        "sourcePostUrl": "https://videos.example.test/posts/accepted",
        "professionalAcquisitionReceiptRef": f"receipts/{'b' * 64}.json",
        "professionalAssetId": "accepted",
        "professionalContentSha256": digest,
        "platform": "Pexels Videos",
        "title": "西湖旅行实拍",
        "relevance": "西湖旅行实景",
        "originalCreatorName": "Creator",
        "attributionText": "西湖旅行实拍 — Creator",
        "rightsBasis": "platform rights pending verification",
        "rightsStatus": "unverified",
        "rightsIssues": ["commercial authorization is unverified"],
        "commercialAuthorizationStatus": "unverified",
        "termsUrl": "https://videos.example.test/terms",
        "authorizationProofUrl": "",
        "modelReleaseStatus": "unverified",
        "propertyReleaseStatus": "not_required",
    }


def test_cli_preflight_bootstrap_does_not_import_video_probe_dependencies() -> None:
    result = _run_cli_with_blocked_imageio("task", "preflight", "--help")
    assert result.returncode == 0, result.stderr
    assert "--no-semantic-agent-credential" in result.stdout


def test_acquire_video_reports_typed_missing_probe_dependency() -> None:
    result = _run_cli_with_blocked_imageio(
        "task",
        "acquire-videos",
        "--manifest",
        "missing-manifest.json",
        "--handoff-ref",
        "missing-handoff.json",
    )
    assert result.returncode != 0
    assert "DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING" in result.stderr
    assert "dependency=imageio_ffmpeg" in result.stderr


def test_fetch_seam_consumes_receipt_bound_cas_without_network_refetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    shared = tmp_path / "execution-shared"
    cas_path = tmp_path / "cas.mp4"
    cas_path.write_bytes(b"receipt-bound-video-bytes")
    captured: list[Path] = []
    marker = tmp_path / "evidence.json"

    monkeypatch.setattr(handler_fetch_video, "execution_shared_dir", lambda _execution: shared)
    monkeypatch.setattr(
        handler_fetch_video,
        "resolve_professional_video_candidate",
        lambda _candidate, *, root: cas_path,
    )
    monkeypatch.setattr(
        handler_fetch_video,
        "_download_sourced_video",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("receipt-bound CAS must not refetch network bytes")
        ),
    )
    monkeypatch.setattr(
        handler_fetch_video,
        "probe_audio_stream",
        lambda _path: {"hasAudio": False},
    )

    def fake_write(**kwargs: object) -> Path:
        captured.append(Path(kwargs["source_video_path"]))
        return marker

    monkeypatch.setattr(
        handler_fetch_video,
        "write_admitted_sourced_video_unit",
        fake_write,
    )
    result = handler_fetch_video.fetch_admitted_sourced_videos(
        execution_id="20260805--travel-video-m100--test--scale-001",
        entity_id="西湖",
        entity_type="地点/景区",
        candidates=[candidate],
        professional_acquisition_root=tmp_path,
    )
    assert result == [marker]
    assert captured == [cas_path]
    assert cas_path.is_file()
    evidence = next(
        (shared / "professional_video_acquisition_consumption").glob("*.json")
    )
    payload = read_json(evidence)
    assert payload["downloadOutcome"] == "admitted"
    assert payload["acquisitionReceiptRef"] == candidate[
        "professionalAcquisitionReceiptRef"
    ]
    with pytest.raises(ValueError, match="frozen capsule.*professional_acquisition_root"):
        handler_fetch_video.fetch_admitted_sourced_videos(
            execution_id="20260805--travel-video-m100--test--scale-001",
            entity_id="西湖",
            entity_type="地点/景区",
            candidates=[candidate],
        )


def test_transport_rejects_credentials_and_manual_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="credential-like"):
        _validated_https_url(
            "https://cdn.example.test/video.mp4?access_token=secret",
            allow_signed_query=False,
        )
    with pytest.raises(ValueError, match="private address"):
        _validated_https_url(
            "https://127.0.0.1/video.mp4",
            allow_signed_query=False,
        )
    with pytest.raises(ValueError, match="escapes"):
        copy_manual_video(
            "../outside.mp4",
            tmp_path / "copy.mp4",
            manual_root=tmp_path,
        )
    redacted = redact_sensitive_video_url(
        "https://cdn.example.test/video.mp4?signature=secret-value&id=123"
    )
    assert "secret-value" not in redacted
    assert "signature=REDACTED" in redacted
    assert "user:password" not in redact_sensitive_video_url(
        "https://user:password@cdn.example.test/video.mp4"
    )


def test_receipt_store_is_create_once_under_concurrent_writers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_digest = "sha256:" + "c" * 64
    stable: dict[str, object] = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": "concurrent-store",
        "manifestDigest": manifest_digest,
        "sourceRevision": "revision-1",
        "sourceDigest": "sha256:" + "d" * 64,
        "entityCatalogDigest": "sha256:" + "e" * 64,
        "plannedAssetCount": 0,
        "discoveredAssetCount": 0,
        "downloadedAssetCount": 0,
        "acceptedAssetCount": 0,
        "rejectedAssetCount": 0,
        "providerAssetCounts": [],
        "assets": [],
    }
    receipt = {**stable, "receiptDigest": document_digest(stable)}
    receipt_path = (
        tmp_path
        / "receipts"
        / f"{manifest_digest.removeprefix('sha256:')}.json"
    )
    monkeypatch.setattr(
        professional_video_store,
        "load_professional_video_acquisition_receipt",
        lambda receipt_ref, *, root: read_json(root / receipt_ref),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: write_create_once_video_receipt(
                    receipt_path,
                    receipt,
                    output_root=tmp_path,
                ),
                range(2),
            )
        )

    assert results == [receipt, receipt]
    collision_stable = {**stable, "sourceRevision": "revision-2"}
    collision = {
        **collision_stable,
        "receiptDigest": document_digest(collision_stable),
    }
    with pytest.raises(ValueError, match="receipt collision"):
        write_create_once_video_receipt(
            receipt_path,
            collision,
            output_root=tmp_path,
        )


def test_network_transport_retries_only_with_governed_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts: list[int] = []

    def fetch_once(*_args: object, **_kwargs: object) -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise OSError("transient reset")
        return ".mp4"

    monkeypatch.setattr(
        professional_video_transport,
        "active_runtime_policy",
        lambda: type(
            "Policy",
            (),
            {"download_fetch_retry_limit": 1, "curl_retry_delay_seconds": 1},
        )(),
    )
    monkeypatch.setattr(
        professional_video_transport,
        "_fetch_public_video_once",
        fetch_once,
    )
    monkeypatch.setattr(professional_video_transport.time, "sleep", lambda _delay: None)
    assert professional_video_transport.fetch_public_video(
        "https://cdn.example.test/video.mp4",
        tmp_path / "video.mp4",
        supported_api=False,
    ) == ".mp4"
    assert attempts == [1, 2]

"""Content-addressed identity derivation for the ReliableTask observer binary."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from core.paths import REPO_ROOT


OBSERVER_BINARY_CACHE_REF = Path(
    "data/local/cache/reliabletask-observer-binaries"
)
OBSERVER_BINARY_NAME = "data-content-worker"


def canonical_digest(document: Mapping[str, object], *, excluded: str) -> str:
    stable = dict(document)
    stable.pop(excluded, None)
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def observer_source_digest() -> str:
    """Over-invalidate safely when any Service Go source or module input changes."""
    service_root = REPO_ROOT / "quwoquan_service"
    inputs = [service_root / "go.mod", service_root / "go.sum"]
    inputs.extend(
        path
        for path in sorted(service_root.rglob("*.go"))
        if not path.name.endswith("_test.go")
    )
    digest = hashlib.sha256()
    for path in inputs:
        if not path.is_file() or path.is_symlink():
            raise OSError(
                "repository Service build input is missing or symbolic"
            )
        relative = path.relative_to(service_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def binary_cache_ref(source_digest: str) -> str:
    return (
        OBSERVER_BINARY_CACHE_REF
        / source_digest.removeprefix("sha256:")
        / OBSERVER_BINARY_NAME
    ).as_posix()


def observer_build_attestation_digest(
    *,
    source_digest: str,
    binary_ref: str,
    binary_sha256: str,
) -> str:
    payload = (
        "data-content-worker-observer-build\n"
        f"{source_digest}\n"
        f"{binary_ref}\n"
        f"{binary_sha256}\n"
        "go build -trimpath -buildvcs=false\n"
        "./services/content-service/cmd/data-content-worker\n"
        "CGO_ENABLED=0\n"
        "GOPROXY=off"
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()

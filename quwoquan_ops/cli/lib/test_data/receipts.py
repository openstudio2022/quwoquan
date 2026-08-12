"""Create-once append journal for request, operation, cleanup and timing facts."""

from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .api import ReceiptRef
from .model import canonical_digest


RECEIPT_SCHEMA = "qwq.test_data_receipt.v1"
_FORBIDDEN_KEYS = frozenset(
    {
        "accesstoken",
        "refreshtoken",
        "authorization",
        "otpcode",
        "phone",
        "phonenumber",
        "providersecret",
        "apisecret",
        "clientsecret",
    }
)


@dataclass
class ReceiptJournal:
    root: Path
    case_id: str
    test_data_instance_id: str
    candidate_binding_digest: str
    _sequence: int = 0
    write_ms: int = 0
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _lock_fd: int = field(default=-1, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.case_id.strip() or "/" in self.case_id:
            raise ValueError("case_id must be non-empty and slash-free")
        if not self.test_data_instance_id.strip() or "/" in self.test_data_instance_id:
            raise ValueError("test_data_instance_id must be slash-free")
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".receipt-journal.lock"
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            os.close(descriptor)
            raise RuntimeError(
                "test-data instance already has an active receipt journal"
            ) from exc
        self._lock_fd = descriptor
        existing = sorted(self.root.glob("*.json"))
        if existing:
            self._sequence = max(int(path.stem.split("-", 1)[0]) for path in existing)

    def append(self, kind: str, payload: Mapping[str, Any]) -> ReceiptRef:
        with self._lock:
            if self._lock_fd < 0:
                raise RuntimeError("receipt journal is closed")
            started = time.monotonic()
            if not kind.strip() or "/" in kind:
                raise ValueError("receipt kind must be non-empty and slash-free")
            _reject_secrets(payload)
            self._sequence += 1
            unsigned = {
                "schema": RECEIPT_SCHEMA,
                "sequence": self._sequence,
                "kind": kind,
                "caseId": self.case_id,
                "testDataInstanceId": self.test_data_instance_id,
                "candidateBindingDigest": self.candidate_binding_digest,
                "recordedAt": datetime.now(timezone.utc).isoformat(),
                "payload": dict(payload),
            }
            receipt_digest = canonical_digest(unsigned)
            document = {**unsigned, "receiptDigest": receipt_digest}
            path = self.root / f"{self._sequence:06d}-{kind}.json"
            encoded = (
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8")
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            self.write_ms += max(
                0,
                round((time.monotonic() - started) * 1000),
            )
            return ReceiptRef(path=path, digest=receipt_digest)

    def close(self) -> None:
        with self._lock:
            if self._lock_fd < 0:
                return
            descriptor = self._lock_fd
            self._lock_fd = -1
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def __del__(self) -> None:
        try:
            self.close()
        except (OSError, RuntimeError):
            pass


def _reject_secrets(value: object, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            normalized_name = re.sub(r"[^a-z0-9]", "", name.lower())
            if normalized_name in _FORBIDDEN_KEYS:
                raise ValueError(f"{path} contains forbidden secret field")
            _reject_secrets(item, f"{path}.{name}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")

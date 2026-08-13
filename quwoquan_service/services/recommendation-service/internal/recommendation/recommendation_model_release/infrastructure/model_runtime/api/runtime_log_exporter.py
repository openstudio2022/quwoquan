"""recommendation-service 结构化 runtime log 上云 exporter。

与 Go 舰队 `quwoquan_service/runtime/observability/runtime_log_http_exporter.go`
同语义：有界持久 spool + 指数退避 + TTL 死信 + sha256 幂等键 + machine token。
参数对齐 catalog 常量（spool 2000 / DLQ 500 / TTL 72h / 退避 5..300s）。

- endpoint/token/spool_dir 全空 = 本地/alpha 禁用远端导出；
- 部分配置直接抛错 fail-closed，生产不允许静默缺 spool；
- exporter 自身绝不经 runtime logger 记录，防止反馈环。

wire 与 Go exporter 完全一致：POST {"records": [<flat fields>...]}，
Idempotency-Key = sha256(payload)，X-Runtime-Log-Ingest-Token = machine token。
记录字段是 observability.slim 扁平形态（service.exception.runtime signal）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prometheus_client import Counter, Gauge

SPOOL_MAX_BATCHES = 2000
DEAD_LETTER_MAX_BATCHES = 500
DELIVERY_TTL = timedelta(hours=72)
EXPORT_INTERVAL_SECONDS = 2.0
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 300
RETRY_MAX_EXPONENT = 6
RETRY_JITTER_PERCENT = 25
_SERVICE = "recommendation-service"

runtime_log_export_total = Counter(
    "runtime_log_export_batches_total",
    "Runtime log batches by service and reliable delivery result.",
    ["service", "result"],
)
runtime_log_spool_pending = Gauge(
    "runtime_log_export_spool_pending",
    "Pending durable runtime log spool batches by service.",
    ["service"],
)
runtime_log_dead_letter_pending = Gauge(
    "runtime_log_export_dead_letter_pending",
    "Runtime log dead-letter batches by service.",
    ["service"],
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class _SpooledBatch:
    id: str
    service: str
    created_at: datetime
    expires_at: datetime
    next_attempt_at: datetime
    attempts: int
    last_failure: str
    records: list[dict[str, str]]

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "service": self.service,
                "createdAt": _rfc3339(self.created_at),
                "expiresAt": _rfc3339(self.expires_at),
                "nextAttemptAt": _rfc3339(self.next_attempt_at),
                "attempts": self.attempts,
                "lastFailure": self.last_failure,
                "records": self.records,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def from_json(raw: str) -> "_SpooledBatch":
        data = json.loads(raw)
        batch = _SpooledBatch(
            id=str(data["id"]),
            service=str(data.get("service", "")),
            created_at=_parse_rfc3339(data["createdAt"]),
            expires_at=_parse_rfc3339(data["expiresAt"]),
            next_attempt_at=_parse_rfc3339(data["nextAttemptAt"]),
            attempts=int(data.get("attempts", 0)),
            last_failure=str(data.get("lastFailure", "")),
            records=[
                {str(k): str(v) for k, v in record.items()}
                for record in data.get("records", [])
            ],
        )
        if len(batch.id) != 64 or not batch.service or not batch.records:
            raise ValueError("runtime log spool batch is incomplete")
        return batch


class RuntimeLogExporter:
    """有界持久 runtime log exporter（与 Go HTTPRuntimeLogExporter 同语义）。"""

    def __init__(self, endpoint: str, token: str, spool_dir: str):
        endpoint = endpoint.strip()
        token = token.strip()
        spool_dir = spool_dir.strip()
        self._endpoint = endpoint
        self._token = token
        self._enabled = False
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if not endpoint and not token and not spool_dir:
            return
        if not endpoint or not token or not spool_dir:
            raise ValueError(
                "runtime log exporter endpoint, token and spool dir must be "
                "configured together"
            )
        self._spool_dir = Path(spool_dir)
        self._dead_dir = self._spool_dir / "dead-letter"
        self._dead_dir.mkdir(parents=True, exist_ok=True)
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="runtime-log-exporter", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        if not self._enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.flush_once()

    def export(self, records: list[dict[str, str]]) -> None:
        if not self._enabled or not records:
            return
        payload = json.dumps({"records": records}, ensure_ascii=False).encode("utf-8")
        batch_id = hashlib.sha256(payload).hexdigest()
        now = _utc_now()
        batch = _SpooledBatch(
            id=batch_id,
            service=_SERVICE,
            created_at=now,
            expires_at=now + DELIVERY_TTL,
            next_attempt_at=now,
            attempts=0,
            last_failure="",
            records=records,
        )
        with self._lock:
            path = self._spool_dir / f"{batch_id}.json"
            if path.exists():
                return
            if not self._ensure_capacity_locked(self._batch_critical(records)):
                runtime_log_export_total.labels(_SERVICE, "dropped_capacity").inc()
                return
            self._write_atomic(path, batch)
            runtime_log_export_total.labels(_SERVICE, "spooled").inc()
            self._refresh_gauges_locked()

    def flush_once(self) -> None:
        if not self._enabled:
            return
        with self._flush_lock:
            now = _utc_now()
            for path in self._spool_files(self._spool_dir):
                try:
                    batch = _SpooledBatch.from_json(path.read_text(encoding="utf-8"))
                except (ValueError, KeyError, json.JSONDecodeError):
                    self._move_to_dead_letter(path, None, "spool_corrupt")
                    continue
                if batch.expires_at < now:
                    self._move_to_dead_letter(path, batch, "ttl_expired")
                    runtime_log_export_total.labels(batch.service, "dead_letter_ttl").inc()
                    continue
                if batch.next_attempt_at > now:
                    continue
                result, failure = self._send(batch)
                if result == "delivered":
                    path.unlink(missing_ok=True)
                    runtime_log_export_total.labels(batch.service, "delivered").inc()
                    continue
                if result == "permanent":
                    self._move_to_dead_letter(path, batch, failure)
                    runtime_log_export_total.labels(
                        batch.service, "dead_letter_permanent"
                    ).inc()
                    continue
                batch.attempts += 1
                batch.last_failure = failure[:128]
                batch.next_attempt_at = now + self._retry_delay(batch)
                self._write_atomic(path, batch)
                runtime_log_export_total.labels(batch.service, "retry_scheduled").inc()
            with self._lock:
                self._refresh_gauges_locked()

    # ── 内部实现 ──────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop.wait(EXPORT_INTERVAL_SECONDS):
            try:
                self.flush_once()
            except OSError:
                # spool 目录暂不可用时保持进程存活，下一轮重试。
                continue

    def _send(self, batch: _SpooledBatch) -> tuple[str, str]:
        body = json.dumps({"records": batch.records}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": batch.id,
                "X-Runtime-Log-Ingest-Token": self._token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            return "transient", f"request: {error}"
        if 200 <= status < 300:
            return "delivered", ""
        if status in (401, 408, 425, 429) or status >= 500:
            return "transient", f"http_{status}"
        return "permanent", f"http_{status}"

    def _retry_delay(self, batch: _SpooledBatch) -> timedelta:
        exponent = min(max(batch.attempts - 1, 0), RETRY_MAX_EXPONENT)
        base = min(RETRY_BASE_SECONDS * (1 << exponent), RETRY_MAX_SECONDS)
        jitter_seed = int(batch.id[:8], 16)
        jitter = base * (jitter_seed % RETRY_JITTER_PERCENT) / 100
        return timedelta(seconds=base + jitter)

    def _ensure_capacity_locked(self, critical: bool) -> bool:
        files = self._spool_files(self._spool_dir)
        if len(files) < SPOOL_MAX_BATCHES:
            return True
        for path in files:
            try:
                batch = _SpooledBatch.from_json(path.read_text(encoding="utf-8"))
            except (ValueError, KeyError, json.JSONDecodeError):
                self._move_to_dead_letter(path, None, "spool_corrupt")
                return True
            if not self._batch_critical(batch.records):
                self._move_to_dead_letter(path, batch, "capacity_evicted")
                return True
        if not critical:
            return False
        oldest = files[0]
        try:
            batch = _SpooledBatch.from_json(oldest.read_text(encoding="utf-8"))
        except (ValueError, KeyError, json.JSONDecodeError):
            batch = None
        self._move_to_dead_letter(oldest, batch, "capacity_evicted_critical")
        runtime_log_export_total.labels(_SERVICE, "critical_capacity_evicted").inc()
        return True

    def _move_to_dead_letter(
        self,
        path: Path,
        batch: _SpooledBatch | None,
        failure: str,
    ) -> None:
        batch_id = batch.id if batch is not None else path.stem
        if batch is not None:
            batch.last_failure = failure
            payload = batch.to_json()
        else:
            payload = json.dumps({"id": batch_id, "lastFailure": failure})
        dead_path = self._dead_dir / f"{batch_id}.json"
        try:
            dead_path.write_text(payload, encoding="utf-8")
        except OSError:
            pass
        path.unlink(missing_ok=True)
        dead_files = self._spool_files(self._dead_dir)
        while len(dead_files) > DEAD_LETTER_MAX_BATCHES:
            dead_files[0].unlink(missing_ok=True)
            dead_files = dead_files[1:]

    def _refresh_gauges_locked(self) -> None:
        runtime_log_spool_pending.labels(_SERVICE).set(
            len(self._spool_files(self._spool_dir))
        )
        runtime_log_dead_letter_pending.labels(_SERVICE).set(
            len(self._spool_files(self._dead_dir))
        )

    @staticmethod
    def _spool_files(directory: Path) -> list[Path]:
        try:
            return sorted(
                item for item in directory.iterdir()
                if item.is_file() and item.suffix == ".json"
            )
        except OSError:
            return []

    @staticmethod
    def _batch_critical(records: list[dict[str, str]]) -> bool:
        return any(
            record.get("severity", "").upper() in ("WARN", "ERROR")
            for record in records
        )

    @staticmethod
    def _write_atomic(path: Path, batch: _SpooledBatch) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(batch.to_json(), encoding="utf-8")
        tmp.replace(path)


def _record_id() -> str:
    now = _utc_now()
    entropy = os.urandom(8).hex()
    micros = int(now.timestamp() * 1_000_000)
    return f"r.{_base36(micros)}.{entropy}"


def _base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out: list[str] = []
    while value:
        value, remainder = divmod(value, 36)
        out.append(digits[remainder])
    return "".join(reversed(out))


class RuntimeLogHandler(logging.Handler):
    """把 WARNING/ERROR 级 Python 日志转为 observability.slim 异常记录上云。

    与 Go 舰队 `service.exception.runtime` signal 对齐的扁平 wire 字段；
    message 有界截断，杜绝把自由堆栈塞进索引字段。
    """

    MAX_MESSAGE_BYTES = 2048

    def __init__(self, exporter: RuntimeLogExporter, environment: str):
        super().__init__(level=logging.WARNING)
        self._exporter = exporter
        self._environment = environment.strip()

    def emit(self, record: logging.LogRecord) -> None:
        if not self._exporter.enabled:
            return
        # exporter 自身的失败绝不能再进入 handler（反馈环）。
        if record.name.startswith("runtime_log_exporter"):
            return
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        message = message.encode("utf-8")[: self.MAX_MESSAGE_BYTES].decode(
            "utf-8", errors="ignore"
        ).strip() or record.levelname
        now = _rfc3339(_utc_now())
        fields = {
            "schema": "observability.slim",
            "recordId": _record_id(),
            "occurredAt": now,
            "observedAt": now,
            "logKind": "exception",
            "severity": "ERROR" if record.levelno >= logging.ERROR else "WARN",
            "signal": "service.exception.runtime",
            "message": message,
            "resourceSourceType": "service",
            "resourceService": _SERVICE,
            "errorCode": "RECOMMENDATION.SYSTEM.model_runtime_exception",
        }
        if self._environment:
            fields["resourceEnvironment"] = self._environment
        self._exporter.export([fields])


def build_runtime_log_exporter_from_env() -> RuntimeLogExporter:
    """从环境变量装配；全空禁用（local/alpha），部分配置 fail-closed。"""
    return RuntimeLogExporter(
        endpoint=os.environ.get("RUNTIME_LOG_INGEST_ENDPOINT", ""),
        token=os.environ.get("RUNTIME_LOG_INGEST_TOKEN", ""),
        spool_dir=os.environ.get("RUNTIME_LOG_SPOOL_DIR", ""),
    )

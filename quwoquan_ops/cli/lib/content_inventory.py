"""仅由 stackctl inspect 调用的无账号、公开 GET 内容盘点。"""
from __future__ import annotations

import inspect
import json
import math
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from . import content_api_consumer as consumer
from .content_api_consumer_authority import _DIGEST_RE, _IDENTITY_RE
from .environment_topology import get_target, load_environment_topology, resolve_environment_target_base
from .public_domain_tls import root_certificate_path

CARRIERS = ("article", "image", "video")
SPEC_REF = "specs/feature-tree/platform-ops-governance/spec.md#req-002"
PAGE_BYTES = 2 * 1024 * 1024


class InventoryBlocker(ValueError):
    """报告只保留类型，不复制异常中的 URL、凭据或响应正文。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class InventoryLimits:
    page_size: int = 20
    max_pages: int = 100
    max_bytes: int = 32 * 1024 * 1024
    total_seconds: float = 60.0
    detail_samples: int = 5

    def validate(self) -> None:
        if not (
            1 <= self.page_size <= 20
            and 1 <= self.max_pages <= 10000
            and 1 <= self.max_bytes <= 256 * 1024 * 1024
            and math.isfinite(self.total_seconds)
            and 0 < self.total_seconds <= 600
            and 0 <= self.detail_samples <= 100
        ):
            raise InventoryBlocker("invalid_limits")


def _authority(target: str) -> tuple[str, Path]:
    topology = load_environment_topology()
    environment = str(get_target(topology, target)["env"])
    resolved = resolve_environment_target_base(topology, environment, target_name=target)
    ca_file = root_certificate_path(target)
    if ca_file.is_symlink() or not ca_file.is_file():
        raise InventoryBlocker("tls_ca_unavailable")
    return resolved.api_base, ca_file


def _default_request(**kwargs: Any) -> consumer.HttpObservation:
    # 公共 transport 必须在首个字节/重定向之前施加边界，不能在读完后伪称受限。
    required = {"client_session_id", "max_response_bytes", "deadline_monotonic", "follow_redirects"}
    if not required.issubset(inspect.signature(consumer._default_http_request).parameters):
        raise InventoryBlocker("transport_safety_unavailable")
    return consumer._default_http_request(**kwargs)


def _cell(*, window: bool = False) -> dict[str, Any]:
    return {
        "scope": "session_window_first_page" if window else "public_browse_work",
        "outcome": "unknown",
        **({} if window else {"count": None}),
        "observedCount": None,
        "traversalComplete": False,
        "pagesRead": 0,
        "emptyReason": None,
        "blocker": None,
    }


class _Inventory:
    def __init__(self, report: dict[str, Any], limits: InventoryLimits,
                 request: Callable[..., Any], clock: Callable[[], float]):
        self.report = report
        self.limits = limits
        self.request = request
        self.clock = clock
        self.deadline = clock() + limits.total_seconds
        self.api_base = ""
        self.ca_file = Path()
        self.session = "content-inventory-" + uuid.uuid4().hex
        self.active: tuple[str, str] | None = None
        self.pages = 0
        self.reserved_bytes = 0
        self.posts: dict[str, str] = {}
        self.window_posts: dict[str, str] = {}
        self.assets: set[str] = set()
        self.feed_observed = False

    def get(self, path: str, query: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        remaining = self.deadline - self.clock()
        byte_limit = min(PAGE_BYTES, self.limits.max_bytes - self.reserved_bytes)
        if remaining <= 0:
            raise InventoryBlocker("total_timeout")
        if byte_limit <= 0:
            raise InventoryBlocker("max_bytes")
        # 按请求允许的原始 body 上界扣减；不拿重新序列化后的大小冒充 wire bytes。
        self.reserved_bytes += byte_limit
        try:
            observation = self.request(
                api_base=self.api_base, ca_file=self.ca_file, method="GET", path=path,
                page_id="content.feed.list" if path == "content/feed" else "content.post.get",
                query=query, client_session_id=self.session,
                timeout_seconds=min(12.0, remaining),
                max_response_bytes=byte_limit, deadline_monotonic=self.deadline,
                follow_redirects=False,
            )
        except InventoryBlocker:
            raise
        except TimeoutError as error:
            raise InventoryBlocker("transport_timeout") from error
        except consumer.ContentApiConsumerTransportError as error:
            raise InventoryBlocker("transport_failed") from error
        except consumer.ContentApiConsumerError as error:
            code = "body_limit" if "byte budget" in str(error) else "noncanonical_response"
            raise InventoryBlocker(code) from error
        except (OSError, ValueError, TypeError) as error:
            raise InventoryBlocker("transport_failed") from error
        if self.clock() >= self.deadline:
            raise InventoryBlocker("total_timeout")
        if observation.status != 200:
            raise InventoryBlocker("http_status")
        if observation.method != "GET" or observation.path != "/" + path:
            raise InventoryBlocker("noncanonical_response")
        if not isinstance(observation.payload, Mapping):
            raise InventoryBlocker("noncanonical_response")
        if len(json.dumps(dict(observation.payload), ensure_ascii=False).encode()) > byte_limit:
            raise InventoryBlocker("body_limit")
        return observation.payload

    def feed(self, query: Mapping[str, str], *, carrier: str | None = None,
             continuation: bool = False) -> Mapping[str, Any]:
        if self.pages >= self.limits.max_pages:
            raise InventoryBlocker("max_pages")
        self.pages += 1
        payload = self.get("content/feed", {**query, "limit": str(self.limits.page_size)})
        rows, cards = payload.get("items"), payload.get("objectCards")
        outcome, empty = payload.get("outcome"), payload.get("emptyReason")
        cursor = payload.get("nextCursor")
        feed_id = payload.get("feedRequestId")
        if not (
            isinstance(rows, list) and isinstance(cards, list)
            and all(isinstance(row, Mapping) for row in rows + cards)
            and len(rows) + len(cards) <= self.limits.page_size
            and isinstance(feed_id, str) and feed_id.strip()
            and (cursor is None or isinstance(cursor, str) and 0 < len(cursor) <= 16384)
            and (outcome == "content" and bool(rows or cards) and empty is None
                 or outcome == "empty" and not rows and not cards and cursor is None
                 and isinstance(empty, str)
                 and empty in {"no_active_release", "no_eligible_content", "continuation_end"})
            and (not carrier or not cards)
            and (empty != "continuation_end" or continuation)
        ):
            raise InventoryBlocker("noncanonical_response")
        release, digest = payload.get("releaseId"), payload.get("manifestDigest")
        if empty == "no_active_release":
            if release is not None or digest is not None:
                raise InventoryBlocker("noncanonical_response")
            raise InventoryBlocker("active_changed" if self.active else "no_active_release")
        if not (isinstance(release, str) and _IDENTITY_RE.fullmatch(release)
                and isinstance(digest, str) and _DIGEST_RE.fullmatch(digest)):
            raise InventoryBlocker("noncanonical_response")
        for row in rows:
            post_id, kind = row.get("postId"), row.get("contentType")
            if not (isinstance(post_id, str) and _IDENTITY_RE.fullmatch(post_id)
                    and kind in CARRIERS and (carrier is None or kind == carrier)):
                raise InventoryBlocker("noncanonical_response")
        if len({row["postId"] for row in rows}) != len(rows):
            raise InventoryBlocker("duplicate_post_id")
        identity = (release, digest)
        if self.active is not None and self.active != identity:
            raise InventoryBlocker("active_changed")
        expected = self.report["requestedIdentity"]
        if (expected["releaseId"] and expected["releaseId"] != release
                or expected["manifestDigest"] and expected["manifestDigest"] != digest):
            raise InventoryBlocker("release_mismatch")
        if self.active is None:
            self.active = identity
            self.report["activeIdentity"] = {"releaseId": release, "manifestDigest": digest,
                                             "source": "first_valid_feed_response"}
        self.feed_observed = True
        return payload

    def media(self, row: Mapping[str, Any]) -> None:
        # 仅计显式资产 ID，不把 URL 数量当作唯一资产量，更不隐式申请 signed grant。
        def collect(value: Any) -> None:
            if isinstance(value, str) and _IDENTITY_RE.fullmatch(value):
                self.assets.add(value)
        collect(row.get("mediaAssetId"))
        items = row.get("mediaItems")
        if items is not None and not isinstance(items, list):
            raise InventoryBlocker("noncanonical_media_declaration")
        for item in items or []:
            if not isinstance(item, Mapping):
                raise InventoryBlocker("noncanonical_media_declaration")
            collect(item.get("mediaAssetId"))
            collect(item.get("coverAssetId"))
        manifest = row.get("articleAssetManifest")
        if manifest is not None:
            if not isinstance(manifest, Mapping) or not isinstance(manifest.get("assets"), list):
                raise InventoryBlocker("noncanonical_media_declaration")
            for item in manifest["assets"]:
                if not isinstance(item, Mapping):
                    raise InventoryBlocker("noncanonical_media_declaration")
                collect(item.get("assetId"))

    def browse(self, carrier: str) -> None:
        cell = self.report["typedContent"][carrier]
        query = {"identity": "work", "type": carrier}
        ids: set[str] = set()
        cursors: set[str] = set()
        feed_id: str | None = None
        while True:
            payload = self.feed(query, carrier=carrier, continuation=bool(cursors))
            if feed_id is not None and feed_id != payload["feedRequestId"]:
                raise InventoryBlocker("feed_session_changed")
            feed_id = payload["feedRequestId"]
            new_ids = [row["postId"] for row in payload["items"]]
            if len(new_ids) != len(set(new_ids)) or ids.intersection(new_ids):
                raise InventoryBlocker("duplicate_post_id")
            if any(post_id in self.posts for post_id in new_ids):
                raise InventoryBlocker("post_type_conflict")
            cursor = payload.get("nextCursor")
            if cursor and cursor in cursors:
                raise InventoryBlocker("cursor_loop")
            ids.update(new_ids)
            self.posts.update((post_id, carrier) for post_id in new_ids)
            for row in payload["items"]:
                self.media(row)
            cell.update(observedCount=len(ids), pagesRead=cell["pagesRead"] + 1)
            if not cursor:
                cell.update(outcome="content" if ids else "empty", count=len(ids),
                            traversalComplete=True, emptyReason=payload.get("emptyReason"))
                return
            cursors.add(cursor)
            query.update(cursor=cursor, feedRequestId=feed_id)

    def window(self, name: str, channel: str) -> None:
        payload = self.feed({"sort": "recommend", "channelId": channel})
        ids: dict[str, str] = {}
        for row in payload["items"]:
            post_id, kind = row["postId"], row["contentType"]
            if post_id in ids:
                raise InventoryBlocker("duplicate_post_id")
            previous_kind = self.posts.get(post_id) or self.window_posts.get(post_id)
            if previous_kind is not None and previous_kind != kind:
                raise InventoryBlocker("post_type_conflict")
            ids[post_id] = kind
        self.window_posts.update(ids)
        self.report["windows"][name].update(
            outcome=payload["outcome"], observedCount=len(ids), pagesRead=1,
            objectCardsObservedCount=len(payload["objectCards"]),
            emptyReason=payload.get("emptyReason"), pageObserved=True,
            hasNextPage=bool(payload.get("nextCursor")),
        )

    def details(self) -> None:
        detail = self.report["postDetails"]
        chosen = list(self.posts.items())[:self.limits.detail_samples]
        detail["sampleSize"] = len(chosen)
        for post_id, carrier in chosen:
            payload = self.get("content/posts/" + quote(post_id, safe=""))
            if (payload.get("postId") != post_id or payload.get("contentType") != carrier
                    or payload.get("contentIdentity") != "work"):
                raise InventoryBlocker("post_detail_mismatch")
            self.media(payload)
            detail["observedCount"] = (detail["observedCount"] or 0) + 1
        detail["outcome"] = "observed" if chosen else "notObserved"
        if not chosen and not self.posts:
            detail["observedCount"] = 0
            detail["emptyReason"] = "no_public_browse_posts"
        # 详情本身不携带 activation envelope；不把夹在两次 feed 中的 GET 冒充快照。
        detail["releaseBinding"] = "notProvidedByDetailResponse"
        if chosen:
            self.feed({"identity": "work", "type": "article"})

    def run(self) -> None:
        for carrier in CARRIERS:
            self._run_cell(self.report["typedContent"][carrier], lambda: self.browse(carrier))
        for name, channel in (("recommend", "recommend"), ("premium", "premium_stream")):
            self._run_cell(self.report["windows"][name], lambda: self.window(name, channel))
        try:
            self.details()
        except InventoryBlocker as error:
            self.report["postDetails"].update(outcome="unknown", blocker=error.code)
            raise

    def _run_cell(self, cell: dict[str, Any], action: Callable[[], None]) -> None:
        try:
            action()
        except InventoryBlocker as error:
            cell.update(outcome="unknown", blocker=error.code, traversalComplete=False)
            if "count" in cell:
                cell["count"] = None
            # 任一失败即结束该进程的本次盘点；不 retry、不重建窗口、不拼接新 release。
            raise


def collect_content_inventory(*, target: str, release_id: str = "", manifest_digest: str = "",
                              limits: InventoryLimits | None = None,
                              http_request: Callable[..., Any] | None = None,
                              clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    limits = limits or InventoryLimits()
    report: dict[str, Any] = {
        "schema": "stackctl-content-inventory-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target": target, "apiOrigin": None, "status": "unknown", "firstBlocker": None,
        "inventoryScope": "traversable_public_browse_work_not_ranked_window_or_global_database",
        "countProvenance": "unique_post_ids_from_public_typed_cursor_pages",
        "requestedIdentity": {"releaseId": release_id or None, "manifestDigest": manifest_digest or None},
        "activeIdentity": None,
        "typedContent": {kind: _cell() for kind in CARRIERS},
        "windows": {kind: _cell(window=True) for kind in ("recommend", "premium")},
        "uniquePostCount": None, "traversalComplete": False,
        "postDetails": {"scope": "bounded_sample", "sampleLimit": limits.detail_samples,
                        "sampleSize": 0, "observedCount": None, "outcome": "notObserved",
                        "fullVerification": False},
        "media": {"scope": "declared_assets_in_observed_browse_and_detail_sample",
                  "uniqueAssetCount": None, "outcome": "notObserved",
                  "byteVerification": "notObserved", "accessibleAssetCount": None,
                  "fullVerification": False},
        "limits": {"pageSize": limits.page_size, "maxPages": limits.max_pages,
                   "maxBytes": limits.max_bytes, "totalSeconds": limits.total_seconds},
        "readOnly": {"method": "GET", "authentication": "none", "accountCreated": False,
                     "releaseMutation": False, "samplePlanDerived": False,
                     "environmentStarted": False, "polling": False},
    }
    inventory = _Inventory(report, limits, http_request or _default_request, clock)
    try:
        limits.validate()
        if ((release_id and not _IDENTITY_RE.fullmatch(release_id))
                or (manifest_digest and not _DIGEST_RE.fullmatch(manifest_digest))):
            report["requestedIdentity"] = {"releaseId": None, "manifestDigest": None}
            raise InventoryBlocker("invalid_release_identity")
        try:
            inventory.api_base, inventory.ca_file = _authority(target)
        except (OSError, ValueError, RuntimeError) as error:
            raise InventoryBlocker("canonical_authority_unavailable") from error
        parsed = urlsplit(inventory.api_base)
        report["apiOrigin"] = f"{parsed.scheme}://{parsed.netloc}"
        inventory.run()
        report["status"] = "complete"
    except InventoryBlocker as error:
        report["firstBlocker"] = {"type": error.code}
        report["status"] = "GATE_BLOCK"
        if error.code in {"active_changed", "release_mismatch", "post_type_conflict"}:
            for cell in [*report["typedContent"].values(), *report["windows"].values()]:
                cell.update(outcome="unknown", traversalComplete=False, blocker=error.code,
                            observedCount=None)
                if "count" in cell:
                    cell["count"] = None
            inventory.assets.clear()
            inventory.feed_observed = False
    complete = (report["firstBlocker"] is None
                and all(cell["traversalComplete"] for cell in report["typedContent"].values()))
    report["traversalComplete"] = complete
    report["uniquePostCount"] = len(inventory.posts) if complete else None
    if inventory.feed_observed:
        report["media"].update(uniqueAssetCount=len(inventory.assets), outcome="declared")
    report["budgetUsage"] = {"feedRequests": inventory.pages,
                             "reservedResponseBytesUpperBound": inventory.reserved_bytes,
                             "byteAccounting": "conservative_per_request_admission_reservation"}
    return report

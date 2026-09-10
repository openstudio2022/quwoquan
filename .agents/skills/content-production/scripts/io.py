"""Skill 的有界 I/O；不选择来源、内容或后继步骤。"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from contextlib import contextmanager
from pathlib import Path


class InputError(ValueError):
    """显式输入或取得证据不满足机械约束。"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key(value: str) -> str:
    return digest(value.encode("utf-8"))[:24]


def safe_path(root: Path, relative: str) -> Path:
    root = root.absolute()
    rel = Path(relative)
    if not relative or rel.is_absolute() or ".." in rel.parts:
        raise InputError(f"路径必须在工作区内：{relative}")
    path = root / rel
    for part in (path, *path.parents):
        if part.is_symlink():
            raise InputError(f"拒绝软链接：{part}")
    if not path.is_relative_to(root):
        raise InputError(f"路径越界：{relative}")
    return path


def read_json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise InputError(f"不是普通文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def encode(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write(path: Path, data: bytes, *, replace: bool = False) -> None:
    """默认 create-or-same；只有可重建的下载索引允许原子替换。"""
    safe_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        if path.read_bytes() != data:
            raise InputError(f"已有文件内容不同，使用新的轮次或快照：{path}")
        return
    fd, temporary = tempfile.mkstemp(prefix=".producer-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise InputError(f"并发写入冲突：{path}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def public_https(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(ord(c) < 32 for c in url):
        raise InputError(f"仅接受无凭据的 HTTPS URL：{url}")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local")) or parsed.port not in {None, 443}:
        raise InputError("不接受本机来源地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise InputError("不接受私网来源地址")
    return url


def public_target(url: str) -> None:
    public_https(url)
    parsed = urllib.parse.urlsplit(url)
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise InputError("来源 DNS 不得指向私网或本机")


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


CHUNK_BYTES = 64 * 1024


class TransferError(InputError):
    def __init__(self, message, *, code="SOURCE.ASSET_FAILED", stop_site=False, body=b""):
        super().__init__(message)
        self.code, self.stop_site, self.body = code, stop_site, body


class PartialFailure(InputError):
    def __init__(self, result):
        super().__init__("下载部分失败；成功资产保留，不代表 approved")
        self.result = result


def carrier_path(root: Path, carrier: str, relative: str) -> Path:
    if not Path(relative).parts or Path(relative).parts[0] != carrier:
        raise InputError(f"路径不得引用另一个载体工作区：{relative}")
    return safe_path(root, relative)


def file_hashes(path: Path) -> dict:
    sha256, sha1, size = hashlib.sha256(), hashlib.sha1(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            size += len(chunk)
            sha256.update(chunk)
            sha1.update(chunk)
    return {"sha256": sha256.hexdigest(), "sha1": sha1.hexdigest(), "bytes": size}


def cached_file(root, carrier, asset, row):
    path = carrier_path(root, carrier, row["path"])
    if row.get("acquisition") == "ytdlp_local":
        metadata = carrier_path(root, carrier, row["metadataPath"])
        if file_hashes(metadata)["sha256"] != row["metadataSha256"] or row["sourceUrl"] != asset.get("sourceUrl"):
            raise InputError(f"本地下载元数据漂移：{asset['id']}")
    if row.get("directUrl") != asset.get("directUrl"):
        raise InputError(f"下载缓存来源漂移：{asset['id']}")
    facts = file_hashes(path)
    if any(facts[key] != row[key] for key in ("sha256", "bytes")):
        raise InputError(f"下载缓存摘要漂移：{asset['id']}")
    if asset.get("sha1") and asset["sha1"].lower() != facts["sha1"]:
        raise InputError(f"来源 sha1 漂移：{asset['id']}")
    return path


class Budget:
    def __init__(self, total):
        if total <= 0:
            raise InputError("传输总预算必须为正数")
        self.remaining, self.used = total, 0

    def check(self, expected):
        if self.remaining <= 0 or expected > self.remaining:
            raise TransferError("超过剩余传输预算", code="SOURCE.BUDGET_EXCEEDED")

    def consume(self, size):
        self.remaining -= size
        self.used += size
        if self.remaining < 0:
            raise TransferError("超过传输总预算", code="SOURCE.BUDGET_EXCEEDED")


def store_chunks(path, chunks, budget, max_bytes, expected_sha1=None):
    """临时文件有界写入；摘要核实后 create-or-same，失败清除本次临时文件。"""
    safe_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".producer-", dir=path.parent)
    sha256, sha1, size = hashlib.sha256(), hashlib.sha1(), 0
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in chunks:
                budget.consume(len(chunk))
                size += len(chunk)
                if size > max_bytes:
                    raise TransferError("超过单资产传输预算", code="SOURCE.BUDGET_EXCEEDED")
                sha256.update(chunk)
                sha1.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        facts = {"sha256": sha256.hexdigest(), "bytes": size}
        if not size or (expected_sha1 and sha1.hexdigest() != expected_sha1.lower()):
            raise TransferError("媒体为空或来源 sha1 不符")
        try:
            os.link(temporary, path)
        except FileExistsError:
            if any(file_hashes(path)[key] != value for key, value in facts.items()):
                raise InputError(f"已有文件内容不同：{path}")
        return facts
    finally:
        Path(temporary).unlink(missing_ok=True)


def challenge(body):
    text = body[:CHUNK_BYTES].lower()
    return (b"<html" in text or b"<!doctype html" in text) and any(
        token in text for token in (b"captcha", b"cf-chl-", b"verify you are human", b"access denied", b"challenge-platform")
    )


class Fetcher:
    """一个调用内同站串行；不重试 429/挑战页，不建立跨会话调度器。"""

    def __init__(self, user_agent: str, gap: float = 1.5):
        if not user_agent.strip() or gap < 0:
            raise InputError("需要真实 User-Agent 与非负请求间隔")
        self.user_agent, self.gap = user_agent, gap
        self.last: dict[str, float] = {}

    @contextmanager
    def response(self, url, *, max_bytes):
        public_target(url)
        host = urllib.parse.urlsplit(url).netloc
        time.sleep(max(0, self.gap - (time.monotonic() - self.last.get(host, 0))))
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.build_opener(_Redirect()).open(request, timeout=60) as response:
                yield response
        except urllib.error.HTTPError as error:
            with error:
                body = error.read(min(CHUNK_BYTES, max_bytes))
            stopped = error.code in {429, 503} or challenge(body)
            raise TransferError(f"HTTP {error.code}: {url}", code=f"SOURCE.HTTP_{error.code}", stop_site=stopped, body=body) from error
        finally:
            self.last[host] = time.monotonic()

    def chunks(self, url, *, max_bytes):
        if max_bytes <= 0:
            raise InputError("max_bytes 必须为正数")
        with self.response(url, max_bytes=max_bytes) as response:
            if int(response.headers.get("Content-Length") or 0) > max_bytes:
                raise TransferError("来源超过本次传输预算", code="SOURCE.BUDGET_EXCEEDED")
            received = 0
            while chunk := response.read(min(CHUNK_BYTES, max_bytes - received + 1)):
                if received == 0 and challenge(chunk):
                    raise TransferError("来源返回技术挑战页", code="SOURCE.CHALLENGE", stop_site=True, body=chunk)
                received += len(chunk)
                yield chunk
                if received > max_bytes:
                    raise TransferError("来源超过本次传输预算", code="SOURCE.BUDGET_EXCEEDED")

    def get(self, url: str, *, max_bytes: int = 16 * 1024 * 1024) -> bytes:
        return b"".join(self.chunks(url, max_bytes=max_bytes))

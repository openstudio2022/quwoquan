#!/usr/bin/env python3
"""供应商中立的权威 DNS 记录写入接口。

记录模型只使用中立形状：`{type, name(FQDN), content, ttl, priority?, data?}`。
provider 负责把中立记录翻译为自身 API 形状，并把自身记录标识回填为中立的
`providerRecordId`。上层（`domain_governance.py`）不感知具体厂商。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any


class DnsProviderError(RuntimeError):
    pass


def record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """中立记录身份：同一 (type, name, value) 视为同一条记录。

    期望侧的结构化记录（CAA 的 `data`）与实况侧的线上文本（`content`）必须归一到
    同一形状，否则同一条 CAA 在两侧算出两个身份，收敛会把稳态误判为漂移。
    """
    record_type = str(record["type"]).upper()
    if record_type == "CAA":
        value = record.get("data")
        text = caa_value(value) if isinstance(value, dict) else str(
            record.get("content") or ""
        )
        canonical = _canonical_caa_text(text)
    else:
        value = record.get("data")
        if value is None:
            value = record.get("content")
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return (
        record_type,
        str(record["name"]).rstrip(".").lower(),
        canonical,
    )


def relative_name(fqdn: str, zone: str) -> str:
    """把 FQDN 折算为 zone 内相对名；apex 用 `@`。"""
    name = str(fqdn).rstrip(".").lower()
    suffix = str(zone).rstrip(".").lower()
    if name == suffix:
        return "@"
    if not name.endswith(f".{suffix}"):
        raise DnsProviderError(f"{fqdn} does not belong to zone {zone}")
    return name[: -(len(suffix) + 1)]


def caa_value(data: dict[str, Any]) -> str:
    """CAA 的线上表示（provider 与 DoH 证据共用同一文本形状）。"""
    return f"{int(data['flags'])} {data['tag']} \"{data['value']}\""


def parse_caa_text(text: str) -> tuple[int, str, str] | None:
    """把 CAA 的线上文本解析为 (flags, tag, value)。

    解析不出三元组时返回 `None`（在场但不是可识别的 CAA），调用方据此判定，不得
    把它当成解析成功的空值。
    """
    parts = str(text).strip().split(None, 2)
    if len(parts) != 3:
        return None
    flags_text, tag, raw_value = parts
    try:
        flags = int(flags_text)
    except ValueError:
        return None
    return flags, tag.strip().lower(), raw_value.strip().strip('"')


def _canonical_caa_text(text: str) -> str:
    parsed = parse_caa_text(text)
    if parsed is None:
        return json.dumps(str(text).strip(), ensure_ascii=False)
    flags, tag, value = parsed
    return json.dumps(f"{flags} {tag} {value}", ensure_ascii=False)


class DnsProvider:
    """权威 DNS 写入面。只暴露上层需要的四个动作。"""

    kind = ""
    # 该服务商自有主机名的判别标记，供上层断言公共解析器与权威侧相互独立。
    vendor_hostname_tokens: tuple[str, ...] = ()

    @classmethod
    def challenge_environment(cls, credential: str, mapping: dict[str, str]) -> dict[str, str]:
        """把中立凭据投影为 ACME 客户端所需的环境变量。

        凭据形状是服务商知识，因此归属 provider；中立层只声明「变量名 -> 部件名」。
        """
        raise NotImplementedError

    def list_records(self, *, name: str, record_type: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_zone_records(self) -> list[dict[str, Any]]:
        """列举 zone 内全部记录，供计划面之外的入口审计。"""
        raise NotImplementedError

    def create_record(self, record: dict[str, Any]) -> str:
        raise NotImplementedError

    def update_record(self, provider_record_id: str, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_record(self, provider_record_id: str) -> None:
        raise NotImplementedError


def _percent_encode(value: str) -> str:
    encoded = urllib.parse.quote(str(value), safe="")
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


class AliyunDnsProvider(DnsProvider):
    """阿里云云解析（Alidns）RPC 接口实现。

    凭据由中立变量承载，值形状为 `<accessKeyId>:<accessKeySecret>`；zone 标识
    在本 provider 语义下即主域名（`DomainName`）。
    """

    kind = "aliyun-dns"
    endpoint = "https://alidns.aliyuncs.com/"
    api_version = "2015-01-09"
    vendor_hostname_tokens = ("alidns.com", "aliyun.com", "aliyuncs.com")

    @classmethod
    def _credential_parts(cls, credential: str) -> dict[str, str]:
        access_key_id, separator, access_key_secret = str(credential).partition(":")
        if not separator or not access_key_id.strip() or not access_key_secret.strip():
            raise DnsProviderError(
                "GATE_BLOCK: aliyun-dns credential must be "
                "'<accessKeyId>:<accessKeySecret>'"
            )
        return {
            "raw": str(credential).strip(),
            "keyId": access_key_id.strip(),
            "keySecret": access_key_secret.strip(),
        }

    @classmethod
    def challenge_environment(
        cls, credential: str, mapping: dict[str, str]
    ) -> dict[str, str]:
        parts = cls._credential_parts(credential)
        projected: dict[str, str] = {}
        for variable, part in mapping.items():
            if part not in parts:
                raise DnsProviderError(
                    f"GATE_BLOCK: unknown credential part {part!r} for "
                    f"{cls.kind}; known parts: {sorted(parts)}"
                )
            projected[str(variable)] = parts[part]
        return projected

    def __init__(self, *, credential: str, zone: str) -> None:
        parts = self._credential_parts(credential)
        self._access_key_id = parts["keyId"]
        self._access_key_secret = parts["keySecret"]
        self._zone = str(zone).rstrip(".").lower()

    @property
    def zone(self) -> str:
        return self._zone

    def _signature(self, parameters: dict[str, str]) -> str:
        canonical = "&".join(
            f"{_percent_encode(key)}={_percent_encode(parameters[key])}"
            for key in sorted(parameters)
        )
        string_to_sign = "&".join(
            ("GET", _percent_encode("/"), _percent_encode(canonical))
        )
        digest = hmac.new(
            f"{self._access_key_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("ascii")

    def _call(self, action: str, **arguments: str) -> dict[str, Any]:
        parameters = {
            "Action": action,
            "Format": "JSON",
            "Version": self.api_version,
            "AccessKeyId": self._access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": uuid.uuid4().hex,
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **{key: str(value) for key, value in arguments.items() if value != ""},
        }
        parameters["Signature"] = self._signature(parameters)
        query = urllib.parse.urlencode(parameters)
        request = urllib.request.Request(
            f"{self.endpoint}?{query}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                # 限流是可重试的瞬时状态；其余 HTTP 错误立即失败。
                if exc.code == 429 or "Throttling" in detail:
                    last_error = exc
                    time.sleep(1 + attempt)
                    continue
                raise DnsProviderError(
                    f"GATE_BLOCK: aliyun-dns {action} failed ({exc.code}): {detail}"
                ) from exc
            except (OSError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(1 + attempt)
        raise DnsProviderError(
            f"GATE_BLOCK: aliyun-dns {action} unreachable"
        ) from last_error

    def _neutral(self, raw: dict[str, Any]) -> dict[str, Any]:
        record_type = str(raw.get("Type") or "").upper()
        relative = str(raw.get("RR") or "")
        name = (
            self._zone if relative == "@" else f"{relative}.{self._zone}"
        )
        neutral: dict[str, Any] = {
            "type": record_type,
            "name": name,
            "content": str(raw.get("Value") or ""),
            "ttl": int(raw.get("TTL") or 0),
            "providerRecordId": str(raw.get("RecordId") or ""),
        }
        if raw.get("Priority") not in (None, ""):
            neutral["priority"] = int(raw["Priority"])
        return neutral

    def list_records(self, *, name: str, record_type: str) -> list[dict[str, Any]]:
        document = self._call(
            "DescribeSubDomainRecords",
            SubDomain=str(name).rstrip("."),
            Type=str(record_type).upper(),
            DomainName=self._zone,
            PageSize="500",
        )
        rows = ((document.get("DomainRecords") or {}).get("Record")) or []
        return [self._neutral(row) for row in rows if isinstance(row, dict)]

    def list_zone_records(self) -> list[dict[str, Any]]:
        page_size = 100
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            document = self._call(
                "DescribeDomainRecords",
                DomainName=self._zone,
                PageNumber=str(page),
                PageSize=str(page_size),
            )
            rows = ((document.get("DomainRecords") or {}).get("Record")) or []
            records.extend(self._neutral(row) for row in rows if isinstance(row, dict))
            total = int(document.get("TotalCount") or 0)
            if not rows or page * page_size >= total:
                return records
            page += 1

    def _arguments(self, record: dict[str, Any]) -> dict[str, str]:
        record_type = str(record["type"]).upper()
        value = (
            caa_value(record["data"])
            if record_type == "CAA"
            else str(record["content"])
        )
        arguments = {
            "RR": relative_name(str(record["name"]), self._zone),
            "Type": record_type,
            "Value": value,
            "TTL": str(int(record["ttl"])),
        }
        if "priority" in record:
            arguments["Priority"] = str(int(record["priority"]))
        return arguments

    def create_record(self, record: dict[str, Any]) -> str:
        document = self._call(
            "AddDomainRecord",
            DomainName=self._zone,
            **self._arguments(record),
        )
        record_id = str(document.get("RecordId") or "")
        if not record_id:
            raise DnsProviderError(
                "GATE_BLOCK: aliyun-dns AddDomainRecord returned no RecordId"
            )
        return record_id

    def update_record(self, provider_record_id: str, record: dict[str, Any]) -> None:
        self._call(
            "UpdateDomainRecord",
            RecordId=str(provider_record_id),
            **self._arguments(record),
        )

    def delete_record(self, provider_record_id: str) -> None:
        self._call("DeleteDomainRecord", RecordId=str(provider_record_id))


_PROVIDERS: dict[str, type[DnsProvider]] = {
    AliyunDnsProvider.kind: AliyunDnsProvider,
}


def provider_for_kind(kind: str) -> type[DnsProvider]:
    """按 policy 声明的 kind 取 provider 类；未注册的 kind 直接 fail-closed。"""
    provider_class = _PROVIDERS.get(str(kind))
    if provider_class is None:
        raise DnsProviderError(
            f"GATE_BLOCK: unsupported dnsProvider.kind {kind!r}; "
            f"registered: {sorted(_PROVIDERS)}"
        )
    return provider_class


def build_provider(*, kind: str, credential: str, zone: str) -> DnsProvider:
    return provider_for_kind(kind)(credential=credential, zone=zone)


def registered_kinds() -> list[str]:
    return sorted(_PROVIDERS)

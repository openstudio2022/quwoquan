"""Structured-data parsers for public Pinterest and Tuchong responses."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class RawPublicImageCandidate:
    provider: str
    source_page_url: str
    asset_url: str
    creator: str
    title: str
    original_signal: bool


class _StructuredHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.meta: dict[str, str] = {}
        self._script_depth = 0
        self._script_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "script":
            self._script_depth += 1
            if self._script_depth == 1:
                self._script_parts = []
        elif tag.lower() == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
            ).strip().lower()
            content = attributes.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, content)

    def handle_data(self, data: str) -> None:
        if self._script_depth:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._script_depth:
            return
        self._script_depth -= 1
        if self._script_depth == 0:
            body = "".join(self._script_parts).strip()
            if body:
                self.scripts.append(body)
            self._script_parts = []


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _json_from_script(value: str) -> object | None:
    candidate = value.strip().removesuffix(";")
    if not candidate.startswith(("{", "[")):
        starts = [
            index
            for index in (candidate.find("{"), candidate.find("["))
            if index >= 0
        ]
        if not starts:
            return None
        candidate = candidate[min(starts) :]
    closing = "}" if candidate.startswith("{") else "]"
    end = candidate.rfind(closing)
    if end < 0:
        return None
    try:
        return json.loads(candidate[: end + 1])
    except json.JSONDecodeError:
        return None


def _documents(content_type: str, body: str) -> tuple[list[object], dict[str, str]]:
    if content_type == "application/json":
        try:
            return [json.loads(body)], {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"public discovery JSON is invalid: {exc}") from exc
    parser = _StructuredHtml()
    parser.feed(body)
    documents = [
        document
        for script in parser.scripts
        if (document := _json_from_script(script)) is not None
    ]
    return documents, parser.meta


def _walk(value: object) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _nested_name(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("name", "full_name", "display_name", "username"):
            text = _text(value.get(key))
            if text:
                return text
    return _text(value) if isinstance(value, str) else ""


def _creator(node: Mapping[str, Any]) -> str:
    for key in ("creator", "pinner", "author", "user", "site"):
        name = _nested_name(node.get(key))
        if name:
            return name
    return _text(node.get("creatorName"))


def _title(node: Mapping[str, Any]) -> str:
    for key in ("grid_title", "title", "name", "description", "caption"):
        text = _text(node.get(key))
        if text:
            return text
    return ""


def _provider_page(value: object, *, provider: str) -> str:
    text = _text(value)
    parsed = urlsplit(text)
    host = str(parsed.hostname or "").lower()
    root = "pinterest.com" if provider == "pinterest" else "tuchong.com"
    if parsed.scheme == "https" and (host == root or host.endswith("." + root)):
        return text
    return ""


def _page_url(node: Mapping[str, Any], *, provider: str, fallback: str) -> str:
    for key in ("sourcePageUrl", "pinUrl", "url", "link"):
        if value := _provider_page(node.get(key), provider=provider):
            return value
    identity = _text(node.get("id") or node.get("pin_id"))
    if provider == "pinterest" and identity.isdigit():
        return f"https://www.pinterest.com/pin/{identity}/"
    return fallback


def _pinterest(
    documents: Iterable[object], meta: Mapping[str, str], *, fallback: str
) -> list[RawPublicImageCandidate]:
    rows: list[RawPublicImageCandidate] = []
    for document in documents:
        for node in _walk(document):
            images = node.get("images")
            original = images.get("orig") if isinstance(images, Mapping) else None
            if isinstance(original, Mapping) and _text(original.get("url")):
                rows.append(
                    RawPublicImageCandidate(
                        "pinterest",
                        _page_url(node, provider="pinterest", fallback=fallback),
                        _text(original.get("url")),
                        _creator(node),
                        _title(node),
                        True,
                    )
                )
            elif _text(node.get("contentUrl")):
                rows.append(
                    RawPublicImageCandidate(
                        "pinterest",
                        _page_url(node, provider="pinterest", fallback=fallback),
                        _text(node.get("contentUrl")),
                        _creator(node),
                        _title(node),
                        True,
                    )
                )
    meta_asset = _text(meta.get("og:image"))
    if meta_asset:
        rows.append(
            RawPublicImageCandidate(
                "pinterest",
                fallback,
                meta_asset,
                _text(meta.get("author")),
                _text(meta.get("og:title")),
                "originals" in urlsplit(meta_asset).path.lower(),
            )
        )
    return rows


def _tuchong(
    documents: Iterable[object], meta: Mapping[str, str], *, fallback: str
) -> list[RawPublicImageCandidate]:
    rows: list[RawPublicImageCandidate] = []
    for document in documents:
        for node in _walk(document):
            images = node.get("images")
            if isinstance(images, list):
                for image in images:
                    if not isinstance(image, Mapping):
                        continue
                    original = image.get("source") or image.get("original")
                    asset = original.get("url") if isinstance(original, Mapping) else ""
                    if _text(asset):
                        rows.append(
                            RawPublicImageCandidate(
                                "tuchong",
                                _page_url(node, provider="tuchong", fallback=fallback),
                                _text(asset),
                                _creator(node),
                                _title(node),
                                True,
                            )
                        )
            elif _text(node.get("contentUrl")):
                rows.append(
                    RawPublicImageCandidate(
                        "tuchong",
                        _page_url(node, provider="tuchong", fallback=fallback),
                        _text(node.get("contentUrl")),
                        _creator(node),
                        _title(node),
                        True,
                    )
                )
    meta_asset = _text(meta.get("og:image"))
    if meta_asset:
        rows.append(
            RawPublicImageCandidate(
                "tuchong",
                fallback,
                meta_asset,
                _text(meta.get("author")),
                _text(meta.get("og:title")),
                False,
            )
        )
    return rows


def extract_public_image_candidates(
    *, provider: str, content_type: str, body: str, source_page_url: str
) -> list[RawPublicImageCandidate]:
    documents, meta = _documents(content_type, body)
    if provider == "pinterest":
        return _pinterest(documents, meta, fallback=source_page_url)
    if provider == "tuchong":
        return _tuchong(documents, meta, fallback=source_page_url)
    raise ValueError(f"unsupported public image provider: {provider}")


__all__ = ["RawPublicImageCandidate", "extract_public_image_candidates"]

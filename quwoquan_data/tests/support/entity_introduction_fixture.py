"""Immutable-release entity introduction projection contract.

This test support module models one read-only entity object snapshot after the
release importer has resolved its media authority.  It deliberately exposes no
environment fixture writer, scenario merger, database seed, or command entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

RELATED_IMAGES_HEADING = "相关图片"
INTRODUCTION_ASSET_ROLES = frozenset({"cover", "inline", "related"})

_ASSET_REF_LINE_RE = re.compile(r"^asset://(\S+)\s*$", re.MULTILINE)
_GALLERY_IDS_ATTR_RE = re.compile(
    r'^:::gallery\b[^\n]*\bids="([^"]*)"',
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class IntroductionAsset:
    """One media-authority-resolved asset from an immutable release."""

    asset_id: str
    url: str
    caption: str
    role: str
    source_ref: str = ""


@dataclass(frozen=True, slots=True)
class ImmutableReleaseEntityIntroduction:
    """Minimal entity object needed by the introduction projection."""

    entity_ref: str
    display_name: str
    page_markdown: str
    assets: tuple[IntroductionAsset, ...]
    fallback_summary: str = ""


@dataclass(frozen=True, slots=True)
class IntroductionSection:
    """One typed section projected from canonical page markdown."""

    kind: str
    title: str
    assets: tuple[IntroductionAsset, ...]
    body_markdown: str | None = None


@dataclass(frozen=True, slots=True)
class EntityIntroductionProjection:
    """Read-only introduction view derived from one release object."""

    entity_ref: str
    display_name: str
    cover_url: str
    summary: str
    sections: tuple[IntroductionSection, ...]


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    cut = end + len("\n---\n")
    return text[:cut], text[cut:]


def _frontmatter_cover_asset_id(frontmatter: str) -> str:
    for line in frontmatter.splitlines():
        trimmed = line.strip()
        if not trimmed.startswith("coverImage:"):
            continue
        value = trimmed[len("coverImage:") :].strip().strip("\"'")
        return value.removeprefix("asset://")
    return ""


def _split_chapters(body: str) -> tuple[str, list[tuple[str, str]]]:
    lead_lines: list[str] = []
    chapters: list[tuple[str, list[str]]] = []
    for line in body.split("\n"):
        trimmed = line.strip()
        if trimmed.startswith("## "):
            chapters.append((trimmed[3:].strip(), []))
            continue
        if chapters:
            chapters[-1][1].append(line)
            continue
        if trimmed.startswith("# "):
            continue
        lead_lines.append(line)
    return (
        "\n".join(lead_lines).strip(),
        [(title, "\n".join(lines)) for title, lines in chapters],
    )


def _section_assets(
    section_body: str,
    asset_by_id: dict[str, IntroductionAsset],
    role: str,
) -> tuple[IntroductionAsset, ...]:
    groups: list[tuple[int, list[str]]] = []
    for match in _ASSET_REF_LINE_RE.finditer(section_body):
        groups.append((match.start(), [match.group(1)]))
    for match in _GALLERY_IDS_ATTR_RE.finditer(section_body):
        groups.append((match.start(), match.group(1).split(",")))
    groups.sort(key=lambda item: item[0])

    projected: list[IntroductionAsset] = []
    seen: set[str] = set()
    for _, asset_ids in groups:
        for raw_id in asset_ids:
            asset_id = raw_id.strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            asset = asset_by_id.get(asset_id)
            if asset is not None:
                projected.append(replace(asset, role=role))
    return tuple(projected)


def _first_paragraph_summary(lead: str) -> str:
    for paragraph in lead.split("\n\n"):
        text = paragraph.strip()
        if not text or text.startswith((":::", "asset://")):
            continue
        return text[:120]
    return ""


def project_entity_introduction(
    snapshot: ImmutableReleaseEntityIntroduction,
) -> tuple[EntityIntroductionProjection, tuple[str, ...]]:
    """Purely project one immutable release object into introduction sections."""

    issues: list[str] = []
    asset_by_id: dict[str, IntroductionAsset] = {}
    for asset in snapshot.assets:
        if not asset.url.strip():
            issues.append(
                f"{snapshot.entity_ref}: 资产 {asset.asset_id} 未由 release media authority 解析 URL"
            )
            continue
        if asset.role not in INTRODUCTION_ASSET_ROLES:
            issues.append(
                f"{snapshot.entity_ref}: 资产 {asset.asset_id} role {asset.role!r} 不在 importer 闭集"
            )
            continue
        asset_by_id[asset.asset_id] = asset

    frontmatter, body = _split_frontmatter(snapshot.page_markdown)
    cover_url = ""
    cover_asset_id = _frontmatter_cover_asset_id(frontmatter)
    if cover_asset_id in asset_by_id:
        cover_url = asset_by_id[cover_asset_id].url
    if not cover_url:
        cover_url = next(
            (
                asset.url
                for asset in asset_by_id.values()
                if asset.role == "cover"
            ),
            "",
        )

    lead, chapters = _split_chapters(body)
    sections: list[IntroductionSection] = []
    if lead:
        sections.append(
            IntroductionSection(
                kind="overview",
                title="概况",
                body_markdown=lead,
                assets=_section_assets(lead, asset_by_id, "inline"),
            )
        )
    for chapter_title, chapter_body in chapters:
        if chapter_title == RELATED_IMAGES_HEADING:
            related_assets = _section_assets(
                chapter_body,
                asset_by_id,
                "related",
            )
            if related_assets:
                sections.append(
                    IntroductionSection(
                        kind="relatedImages",
                        title=RELATED_IMAGES_HEADING,
                        assets=related_assets,
                    )
                )
            continue
        sections.append(
            IntroductionSection(
                kind="body",
                title=chapter_title,
                body_markdown=chapter_body.strip(),
                assets=_section_assets(chapter_body, asset_by_id, "inline"),
            )
        )

    return (
        EntityIntroductionProjection(
            entity_ref=snapshot.entity_ref,
            display_name=snapshot.display_name,
            cover_url=cover_url,
            summary=(
                _first_paragraph_summary(lead)
                or snapshot.fallback_summary.strip()[:120]
            ),
            sections=tuple(sections),
        ),
        tuple(issues),
    )


__all__ = [
    "EntityIntroductionProjection",
    "ImmutableReleaseEntityIntroduction",
    "IntroductionAsset",
    "IntroductionSection",
    "project_entity_introduction",
]

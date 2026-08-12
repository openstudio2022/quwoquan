from __future__ import annotations

from types import SimpleNamespace

from content.execution.controller import content_plan_items


class _Scheduler:
    def assign(self, **_kwargs: object) -> dict[str, object]:
        return {"authorId": "image-author"}

    def schedule(self, _assignment: dict[str, object]) -> dict[str, object]:
        return {"mode": "test"}


def _candidate(*, title: str) -> dict[str, object]:
    return {
        "title": title,
        "sourceId": "openverse",
        "caption": "Wuzhen Old City, Shanghai, China",
        "collectionId": "acquisition:manifest:openverse:asset:one",
        "sourceRef": "sources/openverse/source.md",
        "assetRef": "sources/openverse/assets/001.jpg",
    }


def _append(monkeypatch, *, title: str) -> tuple[dict[str, object], dict[str, object]]:
    briefs: list[dict[str, object]] = []
    monkeypatch.setattr(
        content_plan_items,
        "write_brief_object",
        lambda _execution_id, _ref, brief, **_kwargs: briefs.append(dict(brief)),
    )
    items: list[dict[str, object]] = []
    content_plan_items.append_image_plan_items(
        ctx=SimpleNamespace(execution_id="image-execution"),
        scheduler=_Scheduler(),
        entity_type="地点/景区",
        target="乌镇",
        candidates=[_candidate(title=title)],
        items=items,
    )
    return briefs[0], items[0]


def test_image_plan_blanks_provider_identity_title(monkeypatch) -> None:
    brief, item = _append(monkeypatch, title="Openverse")

    assert brief["titleHint"] == ""
    assert item["title"] == ""
    assert item["caption"] == "Wuzhen Old City, Shanghai, China"


def test_image_plan_preserves_real_source_title(monkeypatch) -> None:
    brief, item = _append(monkeypatch, title="Wuzhen Old City")

    assert brief["titleHint"] == "Wuzhen Old City"
    assert item["title"] == "Wuzhen Old City"

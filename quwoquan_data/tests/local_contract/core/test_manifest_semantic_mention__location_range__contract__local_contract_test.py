from __future__ import annotations

from core.schema import load_schema, validate_strict


def test_manifest_semantic_mention_requires_ranges_only_for_body_location() -> None:
    schema = load_schema("content", "post_manifest")
    mention_schema = schema["$defs"]["semanticMention"]
    manifest_mention = {
        "mentionId": "mention_manifest",
        "kind": "entity",
        "surface": "测试景区",
        "location": "manifest",
        "status": "published",
        "targetRef": "/entity/地点/景区/测试景区",
    }

    assert validate_strict(
        manifest_mention,
        mention_schema,
        _root_schema=schema,
    ) == []

    body_mention = {**manifest_mention, "location": "body"}
    issues = validate_strict(body_mention, mention_schema, _root_schema=schema)
    assert any("rangeStart" in issue for issue in issues)
    assert any("rangeEnd" in issue for issue in issues)

    assert validate_strict(
        {**body_mention, "rangeStart": 0, "rangeEnd": 4},
        mention_schema,
        _root_schema=schema,
    ) == []

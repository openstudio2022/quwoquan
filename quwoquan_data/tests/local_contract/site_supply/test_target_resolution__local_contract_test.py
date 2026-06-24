from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



def test_mediawiki_title_match_rejects_short_parent_title_substrings():
    assert not ss._mediawiki_title_matches_query_terms("上海", ["上海科技馆"])
    assert not ss._mediawiki_title_matches_query_terms("黄山市", ["黄山风景区", "黄山"])
    assert ss._mediawiki_title_matches_query_terms("黄山", ["黄山风景区", "黄山"])
    assert ss._mediawiki_title_matches_query_terms("杭州西湖", ["杭州西湖风景区", "杭州西湖"])

def test_known_entity_target_resolution_prefers_exact_over_suffix_alias():
    target = ss._resolve_known_entity_target("九寨沟", expected_entity_type="地点/景区")
    assert target is not None
    assert target["entityType"] == "地点/景区"
    assert target["name"] == "九寨沟"

def test_known_entity_targets_skip_site_supply_dynamic_placeholders(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="site_supply_dynamic_targets_"))
    original_root = ss.DATA_ROOT
    ss._known_coverage_entity_targets.cache_clear()
    try:
        ss.DATA_ROOT = tmp_path
        dynamic_task = tmp_path / "tasks" / "site_supply_dynamic" / "task.yaml"
        dynamic_task.parent.mkdir(parents=True)
        dynamic_task.write_text(
            "\n".join(
                [
                    "schemaVersion: quwoquan.task.spec",
                    "workflowPolicy:",
                    "  siteSupplyDynamicContentPlan: true",
                    "scope:",
                    "  coverageTargets:",
                    "    - entityType: 地点/景区",
                    "      name: 中国",
                ]
            ),
            encoding="utf-8",
        )
        normal_task = tmp_path / "tasks" / "normal" / "task.yaml"
        normal_task.parent.mkdir(parents=True)
        normal_task.write_text(
            "\n".join(
                [
                    "schemaVersion: quwoquan.task.spec",
                    "scope:",
                    "  coverageTargets:",
                    "    - entityType: 地点/景区",
                    "      name: 九寨沟",
                ]
            ),
            encoding="utf-8",
        )

        targets = ss._known_coverage_entity_targets()
        assert "中国" not in targets
        assert targets["九寨沟"][0]["name"] == "九寨沟"
    finally:
        ss.DATA_ROOT = original_root
        ss._known_coverage_entity_targets.cache_clear()

def test_known_entity_target_resolution_uses_explicit_segment_alias_not_containment():
    original = ss._known_coverage_entity_targets
    target = {
        "name": "云台山－神农山－青天河风景区",
        "entityType": "地点/景区",
        "source": "tasks/example/task.yaml",
    }
    try:
        ss._known_coverage_entity_targets = lambda: {
            "云台山－神农山－青天河风景区": (target,),
            "云台山": (target,),
            "神农山": (target,),
            "上海科技馆": (
                {
                    "name": "上海科技馆",
                    "entityType": "地点/景区",
                    "source": "tasks/example/task.yaml",
                },
            ),
            "上海野生动物园": (
                {
                    "name": "上海野生动物园",
                    "entityType": "地点/景区",
                    "source": "tasks/example/task.yaml",
                },
            ),
        }
        assert ss._resolve_known_entity_target(
            "云台山",
            expected_entity_type="地点/景区",
        ) == target
        assert "云台山" in ss._entity_name_aliases("云台山－神农山－青天河风景区")
        assert "福建土楼" in ss._entity_name_aliases("福建土楼（永定·南靖）旅游景区")
        assert "南靖" not in ss._entity_name_aliases("福建土楼（永定·南靖）旅游景区")
        assert "北京" not in ss._entity_name_aliases("北京（通州）大运河文化旅游景区")
        assert ss._resolve_known_entity_target(
            "上海",
            expected_entity_type="地点/景区",
        ) is None
    finally:
        ss._known_coverage_entity_targets = original


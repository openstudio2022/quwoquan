"""asset_id_from_object_key 稳定性/可读性/唯一性（去 /v1/ 段、去长下划线）。"""
from _common.article_package import asset_id_from_object_key


def test_no_long_underscore_run():
    # 旧实现会把中文 topicId 整段塌缩成一长串下划线
    object_key = "media/image/post/稻城亚丁_体验/detail_1.jpg"
    aid = asset_id_from_object_key(object_key)
    assert "________" not in aid
    assert "___" not in aid  # 连续非法字符折叠为单个 _


def test_readable_ascii_tokens_preserved():
    aid = asset_id_from_object_key("media/image/post/稻城亚丁_体验/detail_1.jpg")
    assert aid.startswith("data_asset_")
    # 可读 ASCII token 保留
    assert "media_image_post" in aid
    assert "detail_1_jpg" in aid


def test_no_version_segment():
    # 新 objectKey 不再含 /v1/，旧 id 也不应再出现 v1 段
    aid = asset_id_from_object_key("media/image/post/x/detail_1.jpg")
    assert "_v1_" not in aid


def test_stable_for_same_input():
    k = "media/image/post/洛绒牛场/cover.jpg"
    assert asset_id_from_object_key(k) == asset_id_from_object_key(k)


def test_unique_for_distinct_chinese_topics():
    # 纯中文差异的 topicId 不得撞 id（旧实现会全塌成相同下划线串）
    a = asset_id_from_object_key("media/image/post/稻城亚丁/cover.jpg")
    b = asset_id_from_object_key("media/image/post/洛绒牛场/cover.jpg")
    assert a != b

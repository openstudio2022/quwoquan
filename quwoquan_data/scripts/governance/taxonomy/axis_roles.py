"""标签轴（axisRole）的唯一真相源。

`axisRole` 回答「这个标签所在的轴是什么」。四大 group 是四条正交轴，同一个词落在
不同轴上是正交（「摄影」既是内容主题也是用户兴趣），落在同一条轴上两次就是重复，
必然产生孤儿。`verify/tag_axis_uniqueness.py` 的 R13 据此区分两者。

轴由标签的 group + dimension 唯一决定，所以这里按路径前缀推导，由 bootstrap 写盘时
落到 `_definition.json`。字段显式落盘而不是校验时临时推导，是为了让下游消费者
（召回、交集、聚合页）能直接读到轴，而不必各自复制一份路径规则。

地理标签天然跨层重名（多个省都有「城关区」），整体不纳入轴治理。
"""

from __future__ import annotations

# 允许出现在 _definition.json 的 axisRole 取值。
AXIS_ROLES: dict[str, str] = {
    "topic": "内容主题（Topic）",
    "userInterest": "用户申报的兴趣偏好（Audience/用户/兴趣偏好）",
    "userAttribute": "用户自身属性：职业 / 教育 / 消费特征（Audience/用户 其余）",
    "creatorIdentity": "创作者身份（Audience/创作者）",
    "audienceGroup": "受众聚集形态（Audience/圈子）",
    "entityType": "现实对象的类型骨架（Entity）",
    "contentAngle": "内容的叙述角度（Format/内容角度）",
    "contentFormat": "内容载体与表现手法（Format 其余）",
}

# 前缀越长越优先。
AXIS_RULES: list[tuple[str, str]] = [
    ("Audience/用户/兴趣偏好/", "userInterest"),
    ("Audience/用户/", "userAttribute"),
    ("Audience/创作者/", "creatorIdentity"),
    ("Audience/圈子/", "audienceGroup"),
    ("Entity/", "entityType"),
    ("Format/内容角度/", "contentAngle"),
    ("Format/", "contentFormat"),
    ("Topic/", "topic"),
]

GEO_PREFIX = ("Topic/地理/",)

_SORTED_RULES = sorted(AXIS_RULES, key=lambda rule: -len(rule[0]))


def is_geo(rel: str) -> bool:
    """地理标签豁免轴治理。"""
    return rel.startswith(GEO_PREFIX)


def axis_role_for(rel: str) -> str | None:
    """按标签相对路径推导它所在的轴；无法归轴时返回 None。"""
    if is_geo(rel):
        return None
    for prefix, role in _SORTED_RULES:
        if rel.startswith(prefix):
            return role
    return None

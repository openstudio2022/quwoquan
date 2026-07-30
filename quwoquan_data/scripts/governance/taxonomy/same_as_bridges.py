"""跨维度概念桥（sameAsRefs）的唯一真相源。

四大分组是正交轴，同一个现实概念会在多条轴上各有一个 tagRef：「摄影」在兴趣轴是
`Audience/用户/兴趣偏好/旅行摄影/摄影`，在主题轴是 `Topic/摄影`。推荐侧的
`ClassifyTagDimension` 按路径首段把标签分流到四张独立 affinity 表，scorer 再各自做
精确字符串匹配，因此这两个 tagRef 在系统里毫不相干：用户在冷启动勾选了兴趣轴的
「摄影」，对主题轴的摄影内容加权为零。`PropagateTagHierarchy` 只沿路径前缀上溯，
也跨不过轴的边界。

`sameAsRefs` 就是补这条断链：它声明「这些 tagRef 指的是同一个现实概念」，
推荐侧据此在路径前缀传播之外再做一次跨维度传播。

与 `aliases` 的区别：`aliases` 是同一个节点的口语化说法（自由文本，用于搜索召回扩展），
`sameAsRefs` 是指向另一条轴上另一个节点的 tagRef。

登记原则：
- 只登记**同一个现实概念**，不登记「相关」「上下位」。相关性由推荐模型学，不由标签硬编码。
- 双向自动补全，不需要两边各写一次。
- 目标必须是磁盘上真实存在的 tagRef；悬空引用会被 verify_tag_tree 的 R13 阻断。
"""

from __future__ import annotations

from collections import defaultdict

# 每个元素是一组指同一现实概念的 tagRef。组内两两互为 sameAs。
CONCEPT_BRIDGES: list[tuple[str, ...]] = [
    # ── 旅行摄影：兴趣轴 ↔ 主题轴 ↔ 视觉风格轴 ────────────────────
    ("Audience/用户/兴趣偏好/旅行摄影/摄影", "Topic/摄影"),
    ("Audience/用户/兴趣偏好/旅行摄影/旅行", "Topic/旅行"),
    ("Audience/用户/兴趣偏好/旅行摄影/徒步", "Topic/旅行/玩法/徒步"),
    ("Audience/用户/兴趣偏好/旅行摄影/自驾", "Topic/旅行/出行方式/自驾"),
    ("Audience/用户/兴趣偏好/旅行摄影/人像", "Topic/摄影/人像摄影"),
    ("Audience/用户/兴趣偏好/旅行摄影/风光影像", "Topic/摄影/风光摄影"),
    ("Audience/用户/兴趣偏好/旅行摄影/胶片", "Format/视觉风格/视觉调性/胶片感"),
    ("Audience/用户/兴趣偏好/旅行摄影/古镇", "Topic/旅行/旅行主题/古镇古村"),
    ("Audience/用户/兴趣偏好/旅行摄影/海岛", "Topic/旅行/旅行主题/海岛度假"),
    ("Audience/用户/兴趣偏好/旅行摄影/雪山", "Topic/自然风光/雪山"),
    ("Audience/用户/兴趣偏好/旅行摄影/城市漫游", "Topic/旅行/旅行主题/城市漫步"),

    # ── 生活 ──────────────────────────────────────────────────
    ("Audience/用户/兴趣偏好/生活/美食", "Topic/美食餐饮"),
    ("Audience/用户/兴趣偏好/生活/咖啡", "Topic/美食餐饮/饮品/咖啡"),
    ("Audience/用户/兴趣偏好/生活/宠物", "Topic/宠物动物"),
    ("Audience/用户/兴趣偏好/生活/家居", "Topic/家居生活"),
    ("Audience/用户/兴趣偏好/生活/穿搭", "Topic/时尚穿搭"),
    ("Audience/用户/兴趣偏好/生活/阅读", "Topic/教育成长/阅读写作"),

    # ── 科技 ──────────────────────────────────────────────────
    ("Audience/用户/兴趣偏好/科技/科技趋势", "Topic/科技"),
    ("Audience/用户/兴趣偏好/科技/AI", "Topic/科技/AI技术"),
    ("Audience/用户/兴趣偏好/科技/数码", "Topic/数码"),
    ("Audience/用户/兴趣偏好/科技/编程", "Topic/科技/编程开发"),
    ("Audience/用户/兴趣偏好/科技/机器人", "Topic/科技/机器人"),
    ("Audience/用户/兴趣偏好/科技/创业", "Topic/职场效率/创业经验"),

    # ── 艺术 ──────────────────────────────────────────────────
    ("Audience/用户/兴趣偏好/艺术/电影", "Topic/影视娱乐/电影"),
    ("Audience/用户/兴趣偏好/艺术/音乐", "Topic/影视娱乐/音乐"),
    ("Audience/用户/兴趣偏好/艺术/绘画", "Topic/艺术创作/绘画插画"),
    ("Audience/用户/兴趣偏好/艺术/设计", "Topic/艺术创作/设计创意"),
    ("Audience/用户/兴趣偏好/艺术/建筑", "Topic/历史文化/建筑艺术"),
    ("Audience/用户/兴趣偏好/艺术/手作", "Topic/旅行/玩法/手作工坊"),
    ("Audience/用户/兴趣偏好/艺术/博物馆", "Topic/旅行/玩法/博物馆展览"),

    # ── 校园 ──────────────────────────────────────────────────
    ("Audience/用户/兴趣偏好/校园/校园生活", "Topic/教育成长/校园生活"),
    ("Audience/用户/兴趣偏好/校园/考研", "Topic/教育成长/升学深造/考研"),
    ("Audience/用户/兴趣偏好/校园/毕业季", "Topic/教育成长/校园生活/毕业季"),
    ("Audience/用户/兴趣偏好/校园/实习", "Topic/教育成长/实习求职"),
    ("Audience/用户/兴趣偏好/校园/社团", "Topic/教育成长/校园生活/社团活动"),

    # ── 创作者身份 ↔ 其垂类的主题表达 ─────────────────────────────
    # 身份轴与主题轴指向同一个垂类概念：把「风光摄影师」这个身份与「风光摄影」这个
    # 主题接通，创作者画像才能参与内容侧的召回加权。
    ("Audience/创作者/垂类身份/旅行博主", "Topic/旅行"),
    ("Audience/创作者/垂类身份/风光摄影师", "Topic/摄影/风光摄影"),
    ("Audience/创作者/垂类身份/自驾达人", "Topic/旅行/出行方式/自驾"),

    # ── 同 group 跨 dimension：同行人轴 ↔ 旅行主题轴 ───────────────
    # 两者用词不同（R14 不触发）但指同一件事；路径前缀传播跨不过 dimension 边界。
    ("Topic/旅行/同行人/家庭带娃", "Topic/旅行/旅行主题/亲子游"),
]


def build_bridge_index() -> dict[str, list[str]]:
    """展开成 tagRef -> 同概念的其他 tagRef 列表（双向、去重、有序）。"""
    index: dict[str, set[str]] = defaultdict(set)
    for group in CONCEPT_BRIDGES:
        for ref in group:
            index[ref].update(other for other in group if other != ref)
    return {ref: sorted(others) for ref, others in index.items()}


_INDEX = build_bridge_index()


def same_as_refs_for(tag_ref: str) -> list[str]:
    """返回与该 tagRef 指同一现实概念的其他轴上的 tagRef。"""
    return list(_INDEX.get(tag_ref, ()))

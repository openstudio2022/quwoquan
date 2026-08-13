"""特征画像 Mongo store 的稳定导入面（行数治理后的薄壳）。

实现拆分在同目录兄弟模块：

- ``mongo_store_core``：组合根、集合装配、索引、打分与作者影响力读面。
- ``mongo_store_intersection_writes``：交集投影快照与证据写入。
- ``mongo_store_intersection_reads``：交集读面、社会证明与 rebuild 清点。
- ``mongo_store_profile_writes``：行为/曝光/搜索/标签反馈画像投影写入。

消费者继续 ``from ...infrastructure.mongo_store import MongoFeatureProfileStore``。
"""
from .mongo_store_core import MongoFeatureProfileStore
from .mongo_store_profile_writes import (
    MAX_COLLABORATIVE_NEIGHBORS,
    MAX_HARD_EXCLUSIONS,
    MAX_PROFILE_FEATURE_KEYS,
)

__all__ = [
    "MAX_COLLABORATIVE_NEIGHBORS",
    "MAX_HARD_EXCLUSIONS",
    "MAX_PROFILE_FEATURE_KEYS",
    "MongoFeatureProfileStore",
]

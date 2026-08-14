"""候选索引 Mongo store 的稳定导入面（行数治理后的薄壳）。

实现拆分在同目录兄弟模块：

- ``mongo_store_core``：组合根、集合装配与索引。
- ``mongo_store_lifecycle_writes``：内容候选生命周期、premium 准入与源事件收件箱写入。
- ``mongo_store_gathering_writes``：gathering 候选源事件投影写入。
- ``mongo_store_audience_writes``：账号限制与人物关系投影写入。
- ``mongo_store_ranking_reads``：排序召回读面。

消费者继续 ``from ...infrastructure.mongo_store import MongoCandidateIndexStore``。
"""
from .mongo_store_core import MongoCandidateIndexStore

__all__ = [
    "MongoCandidateIndexStore",
]

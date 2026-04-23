# 术语表

- `AssetRef`：统一媒体对象引用。
- `MediaAsset`：已完成入库的媒体资产实体。
- `objectKey`：对象存储中的规范化路径。
- `variant`：同一资产的派生规格。
- `UserSyncStream`：面向单个用户的统一同步流。
- `syncSeq`：用户同步流中的单调递增序号。
- `Patch`：一次最小变化单元。
- `Gap Fill`：客户端离线后通过 cursor 补齐缺失变化的过程。
- `Hint`：realtime 发出的最小通知，不保证完整状态。

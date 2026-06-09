# 资产 ID 零碰撞承诺规格

## 1. 目标

成品资产 `assetId` 必须满足：

- 全局唯一，不同批次、不同对象、不同角色不会撞。
- 同一批次内可重复运行，重复运行同一对象时返回同一 `assetId`。
- 不维护全局 asset registry，不做全仓扫描查重。
- 文件名可读、可解析，不再使用长前缀或固定补零序号。

## 2. 唯一真相源

- 全局批次号：`runtime/_shared/global_batch_seq.json`
- 批次绑定：`batches/{batch}/batch_manifest.json.globalBatchSeq`
- 批内登记：`batches/{batch}/_shared/asset_id_registry.json`

## 3. 命名格式

```
{entity}_{role}_{globalBatchSeq}_{digest8}
```

- `entity`：实体 token，保留中文与英文数字，折叠其它字符。
- `role`：`cover` / `closing` / `detail`
- `globalBatchSeq`：十进制原样输出，不补零。
- `digest8`：`SHA-1(seed)` 前 8 位十六进制。

示例：

```
峨眉山_cover_42_a1b2c3d4
稻城亚丁_detail_10000000_fedcba98
```

## 4. hash seed

```
seed = globalBatchSeq | ref | entity | role | nonce
```

- `ref` 为对象内稳定引用，不进入文件名。
- `nonce` 默认 `0`，仅在批内发生撞车时递增重算。
- 不再使用 `batchCreatedAt`、`position/seq` 进入 seed。

## 5. 分配流程

1. `task run`、`download`、`produce` 的首次批次写入调用全局批次号分配器。
2. 首次创建 batch manifest 时分配 `globalBatchSeq`，同 `batch_id` resume 不重复分配。
3. 分配 `assetId` 时先查批内 registry 是否已有同 owner key 记录。
4. 若无记录，按 `nonce=0..max_nonce` 逐次尝试。
5. 一旦 registry 已存在同 owner key，直接复用原 `assetId`。

## 6. 批内 registry 语义

`asset_id_registry.json` 仅服务于当前批次：

- `assetIds`：批内已登记的完整 `assetId` 集合。
- `entries`：`ownerKey -> assetId`，用于同批重跑幂等。

owner key 由以下稳定字段构成：

```
{globalBatchSeq}|{ref}|{entity}|{role}
```

## 7. 解析约定

- 必须从右向左解析 `assetId`。
- 最右 8 位是 `digest8`。
- 倒数第二段是 `globalBatchSeq`。
- 倒数第三段是 `role`。
- 剩余左侧全部视为 `entity`。

推荐使用 `parse_post_asset_id()`，禁止按固定宽度截断 entity。

## 8. 兼容边界

- 历史遗留 `data_asset_*` 或旧序号格式仅作为旧产物兼容，不作为新产线目标。
- 新增产线代码、测试、门禁必须使用新格式。

## 9. 验收门

- `python3 quwoquan_data/scripts/verify/verify_asset_id_zero_collision.py --task ... --batch ...`
- `python3 quwoquan_data/tests/common/test_global_batch_seq.py`
- `python3 quwoquan_data/tests/common/test_batch_asset_registry.py`
- `python3 quwoquan_data/tests/common/test_asset_id_stability.py`

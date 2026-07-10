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

## 3. 命名格式（v2：实体_角色_图注_批次号_hash）

```
{entity}_{role}_{caption}_{globalBatchSeq}_{digest8}
```

- `entity`：实体 token，保留中文与英文数字，折叠其它字符。
- `role`：`cover` / `closing` / `detail`
- `caption`：图注 token 段（人可读的语义段，见 §3.1）。
- `globalBatchSeq`：十进制原样输出，不补零。
- `digest8`：`SHA-1(seed)` 前 8 位十六进制。

示例：

```
峨眉山_cover_金顶云海_42_a1b2c3d4
稻城亚丁_detail_牛奶海秋色_10000000_fedcba98
```

### 3.1 caption token 规则与退化降级链

- 清洗：`asset_token()`（保留中文/英文/数字，折叠其它字符）。
- 截断：清洗后 ≤16 字符（超长从左保留 16 字符）。
- 退化判定 `_caption_is_degraded`：清洗后为空、长度 <2、纯数字、
  通用占位词（图/图片/配图/封面/image/img/photo/picture/cover 等）、
  或与实体 token 相同，均视为退化。
- 降级链（依次）：图注 → `sectionSlug`（章节锚）→ `图{ordinal}`（正整数序号）→ 实体 token。
- caption 段永远非空、永远非纯数字（保证与旧 v1 四段格式的解析可区分）。
- caption **不进入** hash seed：图注文案微调不改变 digest；同批幂等由
  registry 的 owner key 复用保证。

### 3.2 旧格式（v1）兼容

- v1 四段格式 `{entity}_{role}_{globalBatchSeq}_{digest8}` 仅作历史产物解析兼容。
- `parse_post_asset_id()` 同时接受 v1/v2，并在返回值中给出 `format` 字段。
- 新产线（build/produce/publish）一律生成 v2；batch 级 assets 命名门
  （`verify_directory_evidence_chain.py`）对新批次成品 assets 强制 v2。

## 4. hash seed

```
seed = globalBatchSeq | ref | entity | role | nonce
```

- `ref` 为对象内稳定引用，不进入文件名。
- `nonce` 默认 `0`，仅在批内发生撞车时递增重算。
- 不再使用 `batchCreatedAt`、`position/seq` 进入 seed。
- caption 不进 seed（见 §3.1）。

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
- v2：`role` 与 `globalBatchSeq` 之间为 `caption` token 段（可含下划线）；
  v1：`role` 直接邻接 `globalBatchSeq`。
- 剩余左侧全部视为 `entity`（可含下划线）。

推荐使用 `parse_post_asset_id()`，禁止按固定宽度截断 entity 或 caption。

## 8. 兼容边界

- 历史遗留 `data_asset_*` 或旧序号格式仅作为旧产物兼容，不作为新产线目标。
- 新增产线代码、测试、门禁必须使用新格式。

## 9. 验收门

- `python3 quwoquan_data/scripts/verify/verify_asset_id_zero_collision.py --task ... --batch ...`
- `python3 quwoquan_data/tests/common/test_global_batch_seq.py`
- `python3 quwoquan_data/tests/common/test_batch_asset_registry.py`
- `python3 quwoquan_data/tests/common/test_asset_id_stability.py`

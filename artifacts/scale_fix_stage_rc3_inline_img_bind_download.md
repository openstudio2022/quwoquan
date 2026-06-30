# RC3 子步 C1/C2：内联图就地同源下载 + 占位绑定 sourceAssetRef

阶段：fix-rc3-inline-img（最关键）— 子步 C1（write_source_unit 绑定）+ C2（下载接线）

## 子步 C1（已提交 52daee23a）：write_source_unit 占位绑定

在铸 `sourceAssetId` 处单一收口"占位→真实资产"绑定：

- 携带 `placeholderId` 的内联图入 `placeholder_to_asset` 表，资产索引记 `inlinePlaceholderId`。
- 落盘后 `bind_inline_source_placeholders` 重写 `source.md`/`source.clean.md`：成功下载的
  `asset://source-inline-NNN` → `asset://{ordinal_kkk}`（段落锚定不变）；未下载成功的
  `source-inline` 占位整块剥离 `:::figure`（杜绝悬空、图文对不上）。
- `snapshotHash` 仍用 pre-bind 内容作稳定 ID 种子（无门回校 source.md 内容）。
- 测试：`test_source_unit_evidence_chain` 新增 inline 绑定例（2 成功绑定 / 1 失败剥离 /
  图文交错保留 / index 带 `inlinePlaceholderId`）。

## 子步 C2（本次）：handler 下载接线

`download/handler_images.py`：

- 新增纯函数 `build_inline_image_candidates(inline_images, *, entity_id)`：把 fetch 的
  `inlineImages` 映射成来源单元图片候选规格（携带 `placeholderId`/`url`/`caption`/`relevance`）；
  许可/出处不在此伪造，由 `_download_source_unit_images` 从来源 spec 继承。
- `_download_source_unit_images` 新增 `extra_candidates` 形参：内联候选与计划 `imageUrls`
  **合并走同一套 权利→抓取→像素→安全→相关性 五道硬门**（同源不绕许可：来源无可发布
  许可的内联图被权利门如实丢弃）；kept 图片 dict 透传 `placeholderId` 回连段落占位。

`download/handler_fetch.py`：

- 抓取后捕获 `fetched["inlineImages"]`；调用 `_download_source_unit_images` 时传
  `extra_candidates=build_inline_image_candidates(...)`。
- 缓存命中（复用更优 cached source）路径清空 `inline_images`，避免对已绑定的 source.md
  二次注入/重复下载/占位错位。

## 端到端链路（RC3 闭环）

```
HTML <img src> → extract_page_text_with_inline_images(正文+inlineImages)
  → fetch_source_payload.inlineImages（绝对URL）
  → build_inline_image_candidates（带 placeholderId）
  → _download_source_unit_images（五道硬门，不绕许可）
  → write_source_unit（assets/ 落图 + 占位绑定真实 sourceAssetId / 失败剥离）
  → source.md 图文交错保留、asset:// 全部可回查
```

## 测试证据（local_contract，离线 hermetic）

- `test_fetch_registry_dispatch.py`：内联 src 捕获/占位对齐/相对解析/data: 跳过/payload
  inlineImages（19 passed）。
- `test_source_unit_evidence_chain.py`：write_source_unit 占位绑定（5 passed，venv + 系统 python3）。
- `test_inline_source_images.py`（新增）：候选映射 + 五道门穿透回连 placeholderId（3 passed）。
- 回归：`test_image_download_gates.py` 6 passed；handler_fetch 导入正常。

## 许可与放量说明（GATE 诚实）

内联同源图能否最终发布，由 vertical `license_policy.yaml`（`requiredImageFields`/
`allowedLicenseKinds`）的权利硬门决定，**不绕许可**。UGC 游记若无可发布许可，其内联图会被
权利门丢弃、占位剥离——这是 item 4（开放许可图库 metadata-first）与 license policy 的治理边界，
属正确行为而非缺陷。单源内联图保留上限沿用 `QWQ_SOURCE_UNIT_MAX_IMAGES_PER_SOURCE`（默认 8，env 可调）。

## 待接入

- `test_inline_source_images.py` 接入 `verify_quwoquan_data.sh`（归并入 fix-gate-wiring）。

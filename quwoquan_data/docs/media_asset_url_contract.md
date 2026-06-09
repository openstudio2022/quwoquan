# 媒体资产 URL 合同

## 目标

`page.md`、`article.md` 和 PC Web HTML 只保存逻辑引用或渲染结果：

- Markdown 真相源使用 `asset://<assetId>`。
- 发布 manifest 保存 `assetId -> objectKey/cdnUrl/sha256/variants`；顶层 `cdnUrl` 是 `display` 兼容别名。
- 环境 URL 由 `CDN_DOMAIN + objectKey` 推导，不从标题、caption、原始文件名或本机路径推导。

## 统一 Asset Schema

数据工程冷启动资产与用户创建资产都必须归一到以下字段：

- `assetId`：文档内逻辑引用 ID，在单篇文档或单个实体主页内唯一。
- `kind`：`image | video | audio | file`。
- `fileName`：发布包内源文件名，仅用于本地闭包检查。
- `objectKey`：媒体库全局对象键，唯一写入主键。
- `cdnUrl`：由当前环境 CDN base 与 `objectKey` 推导出的 HTTPS URL。
- `sha256`：完整文件摘要，格式为 `sha256:<64 hex>`。
- `variants`：同一逻辑资源的展示变体集合，profile 来源于 `quwoquan_service/contracts/metadata/content/post/media_variant_profiles.yaml`。
- `sourceOwner`：`qwq_data | user | fixture`。
- `sourceRef`：稳定业务对象引用，如 `地点/景区/毕棚沟` 或 `posts/article/.../1`。
- `releaseId` / `environment`：环境发布审计边界。

## Object Key 规则

`objectKey` 必须采用内容寻址命名：

```text
media/objects/sha256/<aa>/<bb>/<fullHash>.<ext>
```

示例：

```text
media/objects/sha256/0f/4c/0f4c8b21f3f1d9aa0f4c8b21f3f1d9aa0f4c8b21f3f1d9aa0f4c8b21f3f1d9aa.png
media/objects/sha256/17/a9/17a901bb2cf0c55d17a901bb2cf0c55d17a901bb2cf0c55d17a901bb2cf0c55d.jpg
```

约束：

- 最终物理对象地址只由内容 `sha256` 与稳定扩展名决定。
- `sourceOwner`、`sourceRef`、`releaseId`、`environment` 只属于 manifest 审计层，不参与物理对象键生成。
- 标题、caption、原始文件名和中文实体名不能进入物理对象主键。
- 完整 `sha256` 必须写入 manifest 与 collision ledger；collision ledger 以 `sha256` 为主索引。

## 防覆盖策略

媒体发布阶段必须维护 `publish/media/collision_ledger.json`：

- `sha256` 不存在：允许写入并记录唯一 `objectKey`。
- `sha256` 已存在且 `objectKey` 相同：允许幂等复用。
- `sha256` 已存在但映射到不同 `objectKey`：发布门 BLOCK，禁止出现第二套物理路径。

同一 `assetId` 的文件内容变化时必须生成新的 `sha256` 和新的 `objectKey`，并由最新 manifest 指向新对象。历史 HTML 或旧 release 继续引用旧 `objectKey`，物理对象不可覆盖。

## URL 推导

标准翻译：

```text
asset://<assetId>
-> asset manifest 命中 assetId
-> variants.display.objectKey / variants.display.cdnUrl
-> https://<CDN_DOMAIN>/<objectKey>?x-oss-process=...
```

签名 URL 只能作为访问层结果返回，不能写回 Markdown 真相源。发布包、运行库和 HTML 中不得出现本机绝对路径、临时任务路径或未受控随机 URL。

## 变体契约

图片发布态必须包含：

- `thumbnail`：列表、网格、搜索等省流场景。
- `display`：文章正文与 SEO HTML 默认图。
- `cover`：feed/profile/search 卡片封面。
- `full`：沉浸式 viewer 默认高清图。
- `original`：原始对象登记，`requiresAccess=true`，公开 manifest 中 `cdnUrl` 必须为空。

视频阶段一必须包含：

- `adaptive`：当前可播放 URL；在转码/HLS/DASH 未完成前可回退到源视频 CDN URL。
- `original`：原始视频登记，`requiresAccess=true`，公开 manifest 中 `cdnUrl` 必须为空。

Markdown、HTML 和 article blocks 只引用 `asset://<assetId>`。Web PC HTML 的 `<img>` 默认写 `display` 到 `src`，并保留 `data-asset-id`；点击预览时必须通过 manifest 反查 `full/original`，不得从 `src` 反推原图。

## 运营容量与观测

媒体 release manifest 必须携带运营目标：

- 日访问量目标：`100000`。
- CDN 命中率阈值：`minCdnHitRate >= 0.9`。
- 列表/正文原图请求：`maxInlineOriginalRequests == 0`。
- 发布报告至少跟踪：`cdnHitRate`、`originFetchRate`、`media4xx5xxRate`、`firstImageP95Ms`、`averageImageBytes`、`originalRequestRatio`、`videoFirstFrameP95Ms`、`videoPlaybackErrorRate`。

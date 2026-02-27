# Design: post-create-update

## 1. 设计目标

- 以 metadata-first 方式补齐创作到发布全链路，不再停留在“发现页可展示、创作页未打通”状态。
- 将圈子从权限维度中剥离为分发维度，降低权限组合复杂度。
- 保障发布后内容不可变与删除一致性（作者分发 + 用户转发全部下架）。

## 2. 核心决策

### 2.1 可见性模型简化

- `visibility` 仅保留：`public` / `private`。
- 不再支持 `circle` 可见性。
- 发布到圈子时必须为 `public`，由服务侧校验。

### 2.2 圈子分发与转发分离存储

- 新增 `PostCircleDistribution`：作者主动分发关系（支持发布后追加/移除圈子）。
- 新增 `PostCircleReshare`：用户转发/引用转发关系（与作者主动分发分离）。
- 圈子流查询按 `active` 关系聚合，来源类型可回显（author_distribution / reshare）。

### 2.3 删除级联与墓碑

- 删除 `Post` 时事务内执行：
  1) `Post.status = deleted`
  2) `PostCircleDistribution.state = cascade_deleted`
  3) `PostCircleReshare.state = cascade_deleted`
  4) 写入 `DeletedPostTombstone`
- 详情 URL 读取策略：
  - 主库未命中 -> 查墓碑
  - 命中墓碑 -> 返回“已删除”
  - 未命中墓碑 -> 返回“内容不存在”

### 2.4 四类内容发布规则

- moment：`body` 非必填；`body/mediaUrls/videoUrl` 至少一项有值。
- photo：封面可空，展示侧回退首图。
- video：默认首帧封面；可手工指定封面覆盖。
- article：标题必填；`summary` 模型生成后可编辑；`illustrationAssetId` 可选且最多 1 张。

### 2.5 发布后不可变策略

- `published` 后禁止更新内容本体字段（title/body/media/summary 等）。
- 允许操作：
  - 删除内容
  - 调整作者主动圈子分发关系（add/remove）

## 3. 存储与分发架构

- 文本与关系：MongoDB（Post + Distribution + Reshare + Tombstone）。
- 媒体对象：站点 SSD 作为 origin 存储。
- 访问路径：客户端 -> CDN -> miss 回源 SSD origin。
- 媒体处理：upload complete -> 处理管线（抽帧/转码/元数据提取）-> MediaAsset ready -> 发布可见。

## 4. 事件与读模型

- 新增事件：`PostCircleDistributionUpdated`、`PostReshared`、`PostQuoted`、`PostDeletedCascadeApplied`、`PostTombstoned`、`MediaMetaExtracted`。
- discovery/circle 投影侧需过滤 `deleted` / `cascade_deleted` 状态，避免已删除内容继续曝光。

## 5. 约束

- Metadata YAML 为唯一事实源；codegen 文件禁止手改。
- DDD 依赖方向不变：domain <- application <- adapters <- infrastructure。
- 错误码统一走 `runtime/errors`，端侧经 codegen 映射。

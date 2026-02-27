# L3 特性：post-create-update

## 功能说明
- 建立四类内容（微趣/美图/视频/文章）统一创作与发布契约，补齐端云发布链路。
- 完成权限语义简化：仅 `public/private`；圈子只作为分发关系，不再作为可见性维度。
- 支持作者在发布后变更圈子分发关系（追加/移除），但内容本体不可修改（仅允许删除）。
- 明确作者主动分发与用户转发分离建模，并在删除时做级联下架。
- 引入已删除墓碑库，确保 URL 访问可区分“已删除”与“内容不存在”。

## 范围
- `content/post` 元数据（aggregate/fields/storage/service/events/errors）补齐。
- 文章摘要与插图能力补齐（标题必填、summary 生成后可编辑、插图可选）。
- 媒体上传与处理契约补齐（上传会话、首帧封面、手工封面、元数据提取）。
- 端侧 codegen 契约同步（writable fields、路由、错误码）。
- 子节点 `create-entry-location-visibility-circle` 负责补齐创作页“位置/公开/圈子选择”入口交互与 payload 映射。
- 本节点当前不包含“更多功能按钮反馈”闭环能力（明确排除）。

## 适用范围与约束
- 适用于 discovery-content 下的内容创作与发布主链路（create -> post -> discovery feed）。
- 适用于服务侧可见性与分发语义治理，以及端侧发布参数对齐。
- 不适用于创作后反馈行为（不感兴趣/屏蔽/投诉）策略收敛，该部分在后续节点处理。

## 关键约束
- `moment`：`body` 非必填，但 `body/image/video` 至少一项存在。
- `photo`：可不指定封面，展示可退化到首图。
- `video`：默认首帧封面，可手工指定封面覆盖。
- `article`：标题必填，`summary` 可编辑，`illustrationAssetId` 最多一张可选插图。
- 发布到任一圈子前提：内容为 `public`。
- 内容 `published` 后禁止更新正文/标题/媒体，仅允许删除与圈子分发关系变更。

## 验收标准（概要）
- A1：四类内容校验规则在服务侧一致生效。
- A2：`public/private` 权限模型生效，圈子分发与权限解耦。
- A3：作者分发与用户转发可区分存储与查询。
- A4：删除触发分发与转发级联下架。
- A5：墓碑库命中时返回“已删除”，否则返回“找不到”。
- A6：媒体元数据与设备/地点信息可入库并可回读。
- A7：metadata、OpenAPI 与 codegen 一致通过。
- A8：mock/unit/contract/integration/uat 测试映射完整并通过门禁。

# L3 Story：career-interest-profile-editor — 职业与兴趣资料页闭环 (`career-interest-profile-editor`)

> 所属能力：[`profile-homepage-redesign`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望职业与兴趣资料页端云标签闭环，覆盖标签真相源、端侧 UX、user-service 保存校验与 object_tag_index 投影，从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- /profile/career-interests 独立页面
- Audience/用户/职业 与 Audience/用户/兴趣偏好 标签树
- ListTagChildren / ResolveTag / ValidateTagRefs 查询校验链路
- ReportTagFeedback 标签添加/移除事实链路
- PATCH /user/profile 保存 occupationTagRef 与有序 interestTagRefs
- object_tag_index user 对象投影

### Out of Scope

- 推荐标签模块
- 自由文本标签
- Topic/兴趣 旧路径

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 页面加载与标签同源查询

- 职业与兴趣入口不依赖端侧完整枚举。

<a id="req-002"></a>
### REQ-002 编辑、排序、保存与校验

- PATCH 仅更新触达的职业/兴趣字段，未触达字段不被误清空。

<a id="req-003"></a>
### REQ-003 保存后进入交集索引

- 写时投影与离线 backfill 都使用 object_tag_index 同一结构。
- `objectType + objectId` 是倒排投影的复合身份；不同对象类型不得因同名 ID 合并。
- 数据发布导入以 source owner 的 immutable release 收敛：同 release 不接受不同内容重写，完整新 release 成功后才删除该 owner 的 superseded rows。
- shared-tags、related-objects 等对象关联查询是 service-only 内部能力；端侧只消费公开目录、校验和用户资料结果。

<a id="req-004"></a>
### REQ-004 我的资料页职业与兴趣管理旅程

- 用户能完成职业选择、兴趣添加、排序、保存、回读的完整旅程。

<a id="req-005"></a>
### REQ-005 user-service 保存校验必须拒绝旧 `Topic/兴趣/*`、非职业/兴趣根、职业多选、分类父节点、兴趣超过 30

- user-service 保存校验必须拒绝旧 `Topic/兴趣/*`、非职业/兴趣根、职业多选、分类父节点、兴趣超过 30。
- 全部兴趣：横向分类胶囊 Tab，文字标签卡片右上角 `+`，点击卡片或 `+` 添加
- 标签字体使用常规字重，`+` 与文字之间必须预留空间，不得重叠
- 添加后从全部兴趣隐藏。
- 返回拦截：有未保存修改时使用 iOS 原生风格 `CupertinoAlertDialog`，提供 `保存 / 继续编辑 / 放弃修改`；不得回退为底部动作面板。
- 页面保存失败统一映射 `USER.PROFILE.invalid_tag_ref` 或通用保存失败文案。

## 4. 契约引用

- canonical：`tag-service.ListTagChildren`
- canonical：`tag-service.ResolveTag`
- canonical：`user-service.UpdateUserProfile`
- canonical：`tag-service.ValidateTagRefs`
- canonical：`tag-service.ReportTagFeedback`
- canonical：`tag-service.object_tag_index`
- canonical：`tag-service.SharedTags`
- canonical：`profile-career-interest-personalization`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面加载与标签同源查询

- GIVEN tag-service 已导入职业与兴趣标签树
- GIVEN 用户已有或没有 occupationTagRef / interestTagRefs
- WHEN 用户从编辑资料进入职业与兴趣页
- THEN 职业分类通过 Audience/用户/职业 子节点查询
- THEN 兴趣分类通过 Audience/用户/兴趣偏好 子节点查询
- THEN 已选 tagRef 通过 ResolveTag 补文案
- THEN 端侧无 Topic/兴趣 旧路径依赖

<a id="gwt-002"></a>
### GWT-002 编辑、排序、保存与校验

- GIVEN 我的标签少于 30 个
- WHEN 用户删除兴趣、从全部兴趣添加兴趣并拖拽排序后点击保存
- THEN interestTagRefs 去重保序保存
- THEN 超过 30 个兴趣被拒绝
- THEN Topic/兴趣 与非法职业/兴趣根被 USER.PROFILE.invalid_tag_ref 拒绝
- THEN 标签添加/移除分别以 click/ignore 经 TagFeedbackCommandWriter 追加事实；失败不阻断编辑并进入结构化观测。
- THEN 认证 persona/device 是反馈事实唯一 actor，客户端伪造身份 header 不可写入；事实提交后以稳定 feedback id 至少一次投递 TagFeedbackRecorded，投递失败保留待确认事实并可重试。
- THEN `content-service` 以 `eventId` durable inbox 幂等消费 `TagFeedbackRecorded`：click 写入显式标签亲和度、ignore 移除该显式亲和度、correct 因未携带替换标签仅保留事实而不得臆测偏好；receipt 与特征更新原子提交后才确认流消息，非法信封进入脱敏 DLQ。

<a id="gwt-003"></a>
### GWT-003 保存后进入交集索引

- GIVEN 用户保存职业与兴趣
- WHEN user-service 发布 UserProfileUpdated
- THEN object_tag_index 中 objectType=user 的 tagRefs 包含职业与兴趣
- THEN shared-tags 可用同一 tagRef 计算共同职业/共同兴趣
- THEN 标签发布包完整投影 group/dimension/definition metadata；目录与 dimension 面板只读取 active taxonomy release，不维护应用内维度常量。

<a id="gwt-004"></a>
### GWT-004 我的资料页职业与兴趣管理旅程

- GIVEN 用户在我的资料页点击编辑资料
- WHEN 进入职业与兴趣页，选择职业，添加兴趣，排序并保存
- THEN 返回编辑资料页后 snapshot 回读一致
- THEN 我的主页资料展示与交集解释优先使用靠前兴趣

## 6. 依赖

- 前置要求：[`profile-homepage-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Gamma Remote 标签目录页面实证

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：标签目录、发布导入、资料页和 object_tag_index 已有分层测试；
  Gamma-local 已装配 canonical observability capability，不需要外部日志租户；当前仍
  缺可用物理设备上的 production Remote Patrol CaseResult，静态编译不能冒充真机 UAT。
- 完成判定：`career_interest_reads_remote_tag_catalog` 在 Gamma-local 真机会话中通过并
  产出 CaseResult，页面叶子标签可回溯到 tag-service taxonomy release。

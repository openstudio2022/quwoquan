# L3 规格：career-interest-profile-editor — 职业与兴趣资料页闭环

## Spec Entry

- AppRoot Journey/Scenario: `profile-career-interest-personalization`
- L1_domain_service: `user-identity-profile-relationship`
- L2_business_capability: `profile-homepage-redesign`
- L3_story: `career-interest-profile-editor`
- 验收意图: `GWT / contract / SIT / UAT`
- 测试证据: `local_contract / api_integration / user_acceptance`

## 目标

在“我的资料页”提供独立 `职业与兴趣` 页面，让用户维护事实型职业身份与兴趣标签。职业与兴趣标签必须同源于 tag-service 导入的标签体系，保存后进入 `object_tag_index` 的 `user` 对象索引，用于主页展示、共同职业/共同兴趣解释、推荐权重和小趣助手偏好理解。

## 范围

- 新增端侧路由 `/profile/career-interests` 与页面 `CareerInterestPage`。
- 职业标签根为 `Audience/用户/职业`，V1 保存一个职业叶子 tagRef。
- 兴趣标签根为 `Audience/用户/兴趣偏好`，分类为 `全部 / 旅行摄影 / 校园 / 生活 / 艺术 / 科技`，保存有序叶子 tagRefs，最多 30 个、允许 0 个。
- 查询复用 tag-service `ListTagChildren(parentTagRef)`、`ResolveTag(tagRef)`、`ValidateTagRefs(tagRefs)`。
- 保存复用 user-service `GET /v1/user/profile/edit-snapshot` 与 `PATCH /v1/user/profile`，字段为 `occupationTagRef`、`interestTagRefs` 和派生 `identityTags`。
- user-service 保存校验必须拒绝旧 `Topic/兴趣/*`、非职业/兴趣根、职业多选、分类父节点、兴趣超过 30。
- 保存成功后投影到 Mongo `object_tag_index`：`objectType=user`、`objectId=userId`、`tagRefs=[occupationTagRef, ...interestTagRefs]`。

## Out of Scope

- 不做推荐标签模块。
- 不开放自由文本标签。
- 不新增第二套端侧兴趣枚举。
- 不绕过 tag-service 校验。
- 不改分身管理页或整个编辑资料页结构；仅替换职业与兴趣入口。

## UX / UI

- 顶部：返回箭头、标题 `职业与兴趣`、右侧 `保存`。
- 模块顺序：`职业身份`、`我的标签`、`全部兴趣`。
- 职业身份：白色圆角单行入口，展示 `职业大类 · 叶子职业`，未选中展示 `选择你的职业身份`。
- 我的标签：默认编辑态，4 列文字卡片，右上角 `×` 删除，长按拖拽排序，轻微摇曳；极窄屏可降为 3 列。
- 全部兴趣：横向分类胶囊 Tab，文字标签卡片右上角 `+`，点击卡片或 `+` 添加；添加后从全部兴趣隐藏。
- 返回拦截：有未保存修改时底部弹出 `保存 / 继续编辑 / 放弃修改`。

## 环境集成

- alpha: App mock fixture 与 Service local_contract 使用同一标签根和校验规则。
- beta/gamma: tag-service import 加载 `quwoquan_data/publish/tags`；user-service 保存前走 `ValidateTagRefs`；`object_tag_index` 支持 import/backfill 与写时投影。
- prod: 发布包包含同一标签树、幂等 import/backfill 入口、可回滚的派生索引重建路径。

## 观测与运营

- 页面保存失败统一映射 `USER.PROFILE.invalid_tag_ref` 或通用保存失败文案。
- 指标：保存成功率、保存失败率、invalid_tag_ref 计数、用户兴趣平均数量、`object_tag_index` user 对象覆盖率、shared-tags 共同兴趣非空率。
- SLO: 页面标签层级加载 P95 <= 500ms；保存 P95 <= 800ms；投影失败告警但可通过 backfill 重建。

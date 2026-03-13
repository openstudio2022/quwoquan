# L3 Story：creation-mode-and-surface-ia-unification — 任务列表

## 当前交付任务

> 执行顺序固定为：`metadata -> codegen -> 业务逻辑 -> 测试`

### Phase 1：metadata / codegen 基线

- [ ] **P1**: [metadata] 更新 `content/post/fields.yaml`：为 `Post` 新增 `contentIdentity`、`assistantUsePolicy`，并补齐对应 enum 定义与字段注释
- [ ] **P2**: [metadata] 更新 `content/post/service.yaml`、`content/post/events.yaml`、`content/post/projections/*.yaml`、`content/post/ui_config.yaml`、`social/circle/service.yaml`、`content/post/tests/contract.yaml`，补齐 identity filter、`UpdatePostSettings`、`PromotePostToWork`、share template profile、runtime flag 默认值
- [ ] **P3**: [codegen] 执行 `make -C quwoquan_service verify-metadata && make codegen && make codegen-app`，检查 `content_api_metadata.g.dart`、`content_dtos.dart`、`content_ui_config.g.dart`、`PostBaseDto` 对 identity 语义的承接面

### Phase 2：入口与统一编辑器

- [ ] **P4**: [业务逻辑-端侧] 重构 `CreateEntrySheet` 为三动作入口（`从相册选 / 写点什么 / 拍一下`），保留现有 route id，不再暴露六宫格 taxonomy
- [ ] **P5**: [业务逻辑-端侧] 引入统一 `CreateDraft` / `EditorStartAction` / `IdentitySuggestion` 模型，把 `CreatePage` 从四 Tab 重构为统一编辑器壳层
- [ ] **P6**: [业务逻辑-端侧] 创作链路停止走 `DataService` 裸 endpoint，统一接入 `contentRepositoryProvider`；复用既有 `PublishSettings`、位置选择器、圈子选择器
- [ ] **P7**: [测试-T2/T4] 补齐 unified editor 草稿保留、身份切换、杀进程恢复、弱网自动保存与 round-trip journey 测试

### Phase 3：发布、升级与术语桥接

- [ ] **P8**: [业务逻辑-云侧/端侧] 让 `CreatePost` / `UpdatePost` / `PublishPost` 接受并写入 `contentIdentity`、`assistantUsePolicy`，接入发布前身份建议与显式确认规则
- [ ] **P9**: [业务逻辑-云侧] 实现 `UpdatePostSettings` 与 `PromotePostToWork`，保证发布后可调 `visibility / circleIds / assistantUsePolicy`，并支持 `点滴 -> 作品` 原地升级
- [ ] **P10**: [业务逻辑-端侧] `DiscoveryPage` 改为消费 generated `discovery_rails` 与 `work_format_filters`，统一用户可见文案为 `点滴 / 作品`
- [ ] **P11**: [测试-T1/T2/T3] 补 discovery identity rail contract/widget/integration 测试，验证 rail 切换、作品格式筛选、旧 alias 不再暴露
- [ ] **P12**: [业务逻辑-端侧] `ProfileShell` 收口为 `创作 -> 全部 / 点滴 / 作品`，并在 `作品` 内增加格式筛选，不再直接暴露 `微趣/图片/视频/文字`
- [ ] **P13**: [业务逻辑-端侧] `CircleShell` / `SectionCreations` 收口为与主页同口径的 identity container，并透传 `identity` / `type` 查询参数
- [ ] **P14**: [测试-T1/T2/T3] 补 cross-surface consistency 测试，校验 discovery / profile / circle 同一内容 identity 一致、仅卡片结构差异
- [ ] **P15**: [业务逻辑-端侧] 建立 `笔记 <-> article` 的 UI 术语桥接，统一 `PostBaseDto.displayFormat`、filter label、share title 文案
- [ ] **P16**: [测试-T1/T3] 补 `PromotePostToWork` 的 in-place upgrade 测试，验证 `postId`、deeplink、互动计数、评论线程和渲染类型保持正确

### Phase 4：小趣、权限、生命周期与分享

- [ ] **P17**: [业务逻辑-助手] 建立 content identity 路由规则：`moment -> context memory`、`work -> knowledge index`，并以 tags/summary/title 形成 `guide/checklist` derived tier
- [ ] **P18**: [业务逻辑-端侧/助手] 复用 `skill_consent` 实现“允许小趣使用我的创作内容”总开关，并通过 `assistantUsePolicy=exclude` 支持单条内容排除
- [ ] **P19**: [观测] 建立 launch blocker 指标与事件 schema：入口耗时、身份建议接受率、草稿恢复率、publish/promote 成功率、assistant revoke latency、share 完成率
- [ ] **P20**: [测试-T3/T4] 建立 create-to-publish SLA probe、弱网 profile、草稿恢复、crash-free 关键路径验证
- [ ] **P21**: [发布治理] 把 `A9` 的商用品质指标写入 dashboard / alert / canary gate checklist，并定义扩大灰度的阈值
- [ ] **P22**: [业务逻辑-文档/配置] 清理 legacy visible terminology：旧常量、旧 UI config consumer、旧 surface 文案、旧设计说明引用，确保 precedence matrix 生效
- [ ] **P23**: [测试-T1/T2] 补 precedence audit 与 legacy label regression test，确保 discovery/profile/circle 不再暴露第二套 IA 词表
- [ ] **P24**: [迁移] 实现 `contentIdentity` / `assistantUsePolicy` 双读解析器与历史数据 backfill job，保持旧内容、旧草稿、旧投影可读
- [ ] **P25**: [迁移-T3] 触发 discovery feed、user posts、circle feed、assistant index 的重建与 dry-run 审计，验证回填一致性与重算时延
- [ ] **P26**: [业务逻辑-云侧] 实现 visibility / circle membership / assistant policy 的二次校验与撤销补偿链路，保证 delete / 转私密 / 退圈 / revoke 后资格及时失效
- [ ] **P27**: [测试-T1/T3] 补权限边界、撤销时效、引用标注 integration test，覆盖 `private / circle-visible / public`
- [ ] **P28**: [业务逻辑-端侧] 实现 identity-based share template builder，产出 `moment` 与 `work` 两套 payload、deeplink 与落地页策略
- [ ] **P29**: [测试-T1/T2/T3] 补分享权限与 fallback 测试，覆盖 `private` 禁分享、`circle-visible` 权限受控链接、失败回退到复制链接/保存海报/系统分享

### Phase 5：灰度、回滚与收口

- [ ] **P30**: [发布治理] 在 `GetAppConfig` 与 app providers 中接入五个 runtime kill switch：入口、编辑器、跨面 IA、分享模板、小趣索引
- [ ] **P31**: [发布治理] 接入 `experiment_bucket` 或等效分桶结果，形成 canary matrix：`5% -> 20% -> 50% -> 100%`，并验证每个 flag 的 fallback path
- [ ] **P32**: [验证-T1/T3/T4] 完成 rollback rehearsal、feature flag matrix 演练、gray rollout gate review，并沉淀 `/dev` 收口所需证据

## 搁置任务（带规划）

- [ ] **D1**: 正式化 `contentTier` 持久字段（`normal / featured / guide / checklist`）
  - 搁置原因：当前 Story 先解决 identity 与商用上线问题，不同步引入内容治理工作流
  - 重启条件：精品内容治理 / 攻略模板 / 运营精选能力进入 `/design`

- [ ] **D2**: 外部平台 SDK 级分享接入（微信、朋友圈、微博、小红书）
  - 搁置原因：本 Story 先冻结 payload 与权限契约，不在本批次接各平台 SDK
  - 重启条件：平台分享 story 启动并冻结各平台审核、素材、回调与埋点要求

- [ ] **D3**: 统一 runtime remote config / control-plane 取代 `GetAppConfig` 的局部 flag 承载
  - 搁置原因：当前已有 app config 与 experiment bucket，可支撑首版灰度
  - 重启条件：统一配置中心对移动端 runtime flag 下发能力 ready

## 未来演进任务

- [ ] **E1**: 把 `guide/checklist` 从 derived tier 升级为真正的 content governance contract
- [ ] **E2**: 为小趣引用增加片段级来源面板与用户可见撤销历史
- [ ] **E3**: 为 `PromotePostToWork` 增加更丰富的包装模板（攻略、清单、合集）
- [ ] **E4**: 把 share template 的实验与归因接入统一增长实验体系

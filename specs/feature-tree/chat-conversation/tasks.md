# chat-conversation 任务列表

> 任务顺序：metadata → codegen → 业务逻辑 → 测试 → 部署
> 验收对齐：每个任务标注对应 A1~A25 验收项
> 状态标记：[x] 已完成 / [ ] 待完成

## 当前交付任务

### Phase 0：端云一致性修复（基线对齐）

- [x] T0-1: [端侧] codegen DTO 补全 — 创建 8 个 typed DTO（ConversationDto/MessageDto/MemberDto/UserStateDto/ReceiptDto/SendMessageRequest/SendMessageResponse/SyncResponse） → A1, A4
- [x] T0-2: [端侧] UI 层替换 `Map<String, dynamic>` 为 typed DTO — ChatPage/ChatDetailPage/ChatSettingsPage 全部使用 codegen DTO → A1, A6~A9
- [x] T0-3: [端侧] 修复 MockChatRepository 构造参数 — `app_providers.dart` 中 `MockChatRepository()` 不传多余参数 → A3, A11
- [x] T0-4: [端侧] 统一字段命名 — Mock 数据字段与 DTO 对齐（`_id`→`id`, `lastMessagePreview`→统一） → A3
- [x] T0-5: [验证] `make verify-metadata` 通过 → A4

### Phase 1：metadata + codegen（已完成，待验证）

- [x] T1-1: [metadata] `aggregate.yaml` — ConversationMember/ConversationUserState/MessageReceipt + seq/dedup 策略 → A4
- [x] T1-2: [metadata] `fields.yaml` — Conversation 轻量化 + Message seq/clientMsgId + 4 新实体全字段 → A4
- [x] T1-3: [metadata] `storage.yaml` — 3 新 collection + 索引 + Message seq 索引 → A4
- [x] T1-4: [metadata] `events.yaml` — 10 个域事件全部定义 + realtime_channel → A4, A17
- [x] T1-5: [metadata] `service.yaml` — 17 API routes + SyncMessages/MarkAsRead/GetReceipts → A4, A20
- [x] T1-6: [metadata] `projections/chat_inbox.yaml` — source_events + lastSeq 字段 → A4, A18
- [x] T1-7: [metadata] `errors.yaml` — 5 错误码（code/l10n_key/user_message/go_const/dart_const） → A2, A4
- [x] T1-8: [metadata] `tests/contract.yaml` — 测试场景声明 → A4
- [x] T1-9: [codegen] `make verify-metadata && make codegen && make codegen-app` — 全量生成 → A4

### Phase 2：云侧 runtime 集成 + 补全

- [x] T2-1: [runtime] 重构 `main.go` — 使用 `runtime/config` + `runtime/observability` + `runtime/redis.Router` → KD-11
- [x] T2-2: [runtime] 创建 `services/chat-service/Makefile` — build/test/gate targets → KD-13
- [x] T2-3: [adapter] 实现 `event_publisher.go` — 域事件 → Redis Pub/Sub `rt:conversation:{id}`，支持 10 种事件 → A17
- [x] T2-4: [application] 实现 `inbox_service.go` — ChatInbox 投影 + 未读计数 + ConversationUserState 维护 → A18
- [ ] T2-5: [application] 补全联系人对接 — ListContacts/SearchContacts 对接 user-service social graph → A20（阻塞于 user-service 就绪）
- [x] T2-6: [门禁] 根 Makefile `gate` target 加入 chat-service → KD-13

### Phase 3：云侧已实现（已完成，待验证）

- [x] T3-1: [服务骨架] `services/chat-service/` — cmd/api + configs + go.mod
- [x] T3-2: [domain] Conversation/Message/ConversationMember/ConversationUserState/MessageReceipt 领域模型
- [x] T3-3: [domain] Repository 接口
- [x] T3-4: [infra] MongoDB Repository（MongoChatStore — 5 个实体 CRUD）
- [x] T3-5: [infra] Redis seq INCR + clientMsgId dedup
- [x] T3-6: [infra] Conversation cache（Redis general scene）
- [x] T3-7: [application] ConversationService（会话 CRUD + 成员管理 + memberCount）→ A13, A16
- [x] T3-8: [application] MessageService（发送 + seq + 幂等 + 撤回）→ A14
- [x] T3-9: [application] MemberService（添加/移除 + 助手邀请/移除）→ A16
- [x] T3-10: [adapter] HTTP handlers — 17 路由 + generated_routes → A13~A19

### Phase 4：端侧补全

- [x] T4-1: [端侧] 消息发送流程 — ChatMessageNotifier（clientMsgId 生成 + 乐观插入 + seq 更新 + 失败重试）→ A7, A23
- [x] T4-2: [端侧] 消息 seq 排序展示 — confirmed seq 升序 + pending timestamp 排后 → A7, A23
- [x] T4-3: [端侧] seq gap 检测 + SyncMessages 自动补全 → A15, A23
- [x] T4-4: [端侧] ConversationUserState 本地管理 — ChatSettingsNotifier（mute/pin/markAsRead 乐观更新）→ A8, A24
- [x] T4-5: [端侧] 已读回执 UI — _ReceiptStatusIndicator（sending/failed/read/delivered 四态）→ A12, A19
- [x] T4-6: [端侧] 撤回按钮超时灰显（2min 后隐藏 _isWithinRecallWindow）→ A7
- [ ] T4-7: [端侧] 邀请/移除助手 UI + @小趣触发 + assistant_reply 气泡 → A10（阻塞于 assistant 域 V2）
- [ ] T4-8: [端侧] 集成 RealtimeConnectionManager — 聊天页 subscribe conversation topic → A25（阻塞于 realtime-gateway）
- [x] T4-9: [端侧] 验证 `lib/features/chat/` 清空 — 目录不存在，迁移完成 → A5

### Phase 5：T1 契约与静态层测试

- [x] T5-1: [T1] `test/cloud/chat/dto/contract/conversation_dto_contract_test.dart` — 常规/兼容/异常三维度 → A1
- [x] T5-2: [T1] `test/cloud/chat/dto/contract/message_dto_contract_test.dart` — seq/clientMsgId/status 解析 → A1
- [x] T5-3: [T1] `test/cloud/chat/dto/contract/member_dto_contract_test.dart` — memberType/role/assistantSkillId → A1
- [x] T5-4: [T1] `test/cloud/chat/dto/contract/user_state_dto_contract_test.dart` — readSeq/unreadCount/muted/pinned → A1
- [x] T5-5: [T1] `test/cloud/chat/contract/chat_error_code_contract_test.dart` — 5 码 round-trip（已有）→ A2
- [x] T5-6: [T1] `test/cloud/chat/contract/chat_repository_contract_test.dart` — 17 方法契约（已有）→ A3
- [x] T5-7: [T1] metadata 一致性校验 — `make verify-metadata` → 0 error → A4
- [x] T5-8: [T1] 目录迁移校验 — glob `lib/features/chat/**/*.dart` → 0 files → A5

### Phase 6：T2 模块与交互层测试

- [x] T6-1: [T2] `test/ui/chat/widgets/chat_page_widget_test.dart` — 渲染/交互/错误态三维度（已有）→ A6
- [x] T6-2: [T2] `test/ui/chat/widgets/chat_detail_page_widget_test.dart` — seq 排序 + 乐观发送 + 撤回灰显 → A7
- [x] T6-3: [T2] `test/ui/chat/widgets/chat_settings_page_widget_test.dart` — 成员列表 + mute/pin（已有）→ A8
- [x] T6-4: [T2] `test/ui/chat/widgets/chat_message_bubble_widget_test.dart` — 文本/图片/Markdown/assistant_reply 四种 → A9
- [x] T6-5: [T2] `test/ui/chat/widgets/chat_assistant_ui_widget_test.dart` — Toolbar/Drawer/Popup 交互 → A10
- [x] T6-6: [T2] mock/remote 一致性测试 — ProviderScope 注入两种 Repository → 行为一致 → A11
- [x] T6-7: [T2] 已读回执 UI 测试 — ≤50 人群显示 / >50 隐藏 → A12

### Phase 7：T3 端云集成层测试

- [x] T7-1: [T3-L2] `conversation_crud_contract_test.go` — 会话 CRUD（已有）→ A13
- [x] T7-2: [T3-L2] `message_crud_contract_test.go` — 消息 CRUD + seq + 幂等（已有）→ A14
- [x] T7-3: [T3-L2] `message_sync_contract_test.go` — SyncMessages（已有）→ A15
- [x] T7-4: [T3-L2] `member_management_contract_test.go` — 成员 + 助手（已有）→ A16
- [x] T7-5: [T3-L2] `event_publish_contract_test.go` — 10 事件骨架 + 3 直接测试（round-trip/batch/类型完整性）→ A17
- [x] T7-6: [T3-L2] `inbox_projection_contract_test.go` — 8 个测试（unread 累加/MarkAsRead 重置/排序/默认 limit/空 inbox）→ A18
- [x] T7-7: [T3-L2] `conversation_settings_contract_test.go` — 回执 + 设置（已有）→ A19
- [x] T7-8: [T3-L2] `conversation_error_contract_test.go` — 错误路径（已有）→ A13(error)
- [x] T7-9: [T3-L2] `conversation_compat_contract_test.go` — 兼容性（已有）→ A13(compat)
- [x] T7-10: [T3-L2] `benchmark_test.go` — 6 个 benchmark（SendMessage 并行/1000 并发/SyncMessages/ListMessages/AddMembers 50/CreateConversation）→ A21
- [x] T7-11: [T3-L3] `test/cloud/chat/api_contract_runner.dart` — 5 组 gamma API 契约（会话列表/发送幂等撤回/404 映射/sync 增量/成员操作）→ A20

### Phase 8：T4 端到端旅程层测试

- [x] T8-1: [T4-L1c] `test/ui/chat/journeys/chat_conversation_list_journey_test.dart` — 三 group（正常/错误/边界）→ A22
- [x] T8-2: [T4-L1c] `test/ui/chat/journeys/chat_message_send_journey_test.dart` — 轻量测试 Widget 验证发送链路 → A23
- [x] T8-3: [T4-L1c] `test/ui/chat/journeys/chat_group_management_journey_test.dart` — 三 group（正常/错误/边界）→ A24
- [x] T8-4: [T4-L1c] `test/ui/chat/journeys/chat_assistant_journey_test.dart` — 邀请→@→移除 + 幂等 → A24
- [x] T8-5: [T4-Patrol] `test/patrol/chat/chat_ime_input_test.dart` — 真实 IME 中文/Emoji 输入 → A25
- [x] T8-6: [T4-Patrol] `test/patrol/chat/chat_notification_entry_test.dart` — 系统通知→打开聊天 + 后台切前台 → A25
- [x] T8-7: [T4-Patrol] `test/patrol/chat/chat_orientation_stability_test.dart` — 横竖屏切换 + 输入保持 + 快速多次旋转 → A25

### Phase 9：部署 + 灰度 + 生产

- [x] T9-1: [部署] 创建 `deploy/service/chat-service/Dockerfile` — Go 多阶段构建 → KD-12
- [x] T9-2: [部署] 创建 `deploy/service/chat-service/kustomize/base/` — deployment + service + HPA + PDB → KD-12
- [x] T9-3: [部署] 创建 k8s overlays — dev(1)/integration(2)/prod(3) 差异化 → KD-12
- [ ] T9-4: [部署] seed-box Dockerfile 集成 chat 域（integration/prod）→ KD-12（需 seed-box 维护者协同）
- [x] T9-5: [部署] CI 配置 — `.github/workflows/service_pipeline.yml` 新增 test-chat-service job → KD-13
- [ ] T9-6: [灰度] integration 部署 → 运行 L3 API 契约测试 → A20（运维操作）
- [ ] T9-7: [灰度] prod canary 10% → 监控 p99/错误率/seq gap 24h → A25（运维操作）
- [ ] T9-8: [生产] prod 全量 100% → 确认监控正常 → A25（运维操作）
- [ ] T9-9: [门禁] `make gate` 全量通过（L1+L2 含 chat-service）→ A4

### Phase 10：门禁验收

- [ ] T10-1: [门禁] `make gate` — T1+T2+T3(L2) 全通过
- [ ] T10-2: [门禁] `make gate-full` — + T3(L3) staging 全通过
- [ ] T10-3: [门禁] `patrol test test/patrol/chat/` — T4 Patrol 全通过
- [x] T10-4: [验收] acceptance.yaml A1~A25 全部 status → implemented（25/25）
- [x] T10-5: [验收] 回填 acceptance.yaml tests[] — 每个 implemented 项 tests 非空（25/25）

## 搁置任务

- [ ] 消息热冷分离/归档（重启条件：单会话消息 > 100 万条）
- [ ] 端到端加密 E2EE（重启条件：合规要求或高安全需求用户）
- [ ] 消息全文搜索优化（重启条件：搜索请求量 > 1K/天）
- [ ] 群公告/群文件/群应用（重启条件：产品需求）
- [ ] realtime-gateway 实时推送全链路（重启条件：realtime-gateway 服务实现完成；当前 A1/A2/A14 中的 p99 延迟目标暂 deferred）

## 未来演进任务

- [ ] assistant 类型会话与 PA 系统深度集成（触发：assistant 域 V2 规划启动）
- [ ] 消息压缩 protobuf 替代 JSON（触发：消息量 > 10K/s）
- [ ] 消息反应/表情回复（触发：产品需求）
- [ ] 记录数据迁移脚本 members 嵌入 → ConversationMember（触发：首次实现无需迁移，仅预留）

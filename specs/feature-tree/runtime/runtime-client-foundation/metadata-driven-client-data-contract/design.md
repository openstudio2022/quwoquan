# design：metadata-driven-client-data-contract

## 1. 核心原则

1. **单一真相源**：`contracts/metadata` → `make verify-metadata` / `make codegen-app` → `lib/cloud/runtime/generated/**`。  
2. **边界收口**：HTTP/Mock 边界在 **Repository 实现**；出 Repository 的「领域载荷」优先为 **codegen 类型**（或明确标注的、由 codegen 字段组成的不可变 ViewModel，且字段名与 metadata 一致）。  
3. **Mock ≡ Remote 类型**：`MockXxxRepository` 与 `RemoteXxxRepository` 实现同一 `XxxRepository` 抽象；同一方法返回类型 **完全相同**；Mock 数据通过 `XxxDto.fromMap` 或 `const XxxDto(...)` 构造，与 Remote 解析路径一致。  
4. **UI 层**：列表/详情 **禁止** 以 `List<Map<String,dynamic>>` 作为 **会话、帖子、成员、圈子实体** 的常驻状态类型（过渡期见缺口清单）。

## 2. 与 Provider 的关系

- `app_providers` / `appDataSourceModeProvider` 仅切换 **实现类**，**不**切换返回类型签名。  
- `Ref.read(xxxRepositoryProvider)` 对业务代码透明；Mock/Remote 返回同一抽象上的同一具体类型（或 sealed/union 的 codegen 分支，由 metadata 驱动）。

## 3. 缺口清单（`metadata_driven_ui_gap_inventory.yaml`）

- **domain**：对齐 `contracts/metadata` 或 `lib/cloud/services/{domain}`。  
- **status**：  
  - `compliant`：该域列表/核心页已以 codegen DTO 为主链路。  
  - `partial`：Repository 已类型化，UI 仍部分 Map。  
  - `legacy_map`：UI 或 Mock 仍以 Map 为主。  
- **target_dto**：指向 `generated` 中已有或待补的 codegen 类名（或 `TBD`）。  
- 清单 **允许收缩**：迁移完成后项改为 `compliant` 或可删除；**新增**遗留须登记并附原因/切片号。

## 4. 后续门禁（plan 中实现，非本 baseline 必交付）

- 可选脚本：对 `lib/ui/**/pages/*.dart` 扫描 `List<Map<String, dynamic>>` 与特定 Provider 类型，**仅阻断新增**（基线比对），或按域启用。  
- 与 `make gate` 集成方式同 `verify_ios_native_surface_gate.py`。

## 5. 多态与 content

- Feed/帖子遵循 **`PostBaseDto` 子类** 与仓库规则：**禁止** UI 用 `is`/`as` 判型；差异收口到基类能力位。  
- metadata 新增 post 子类型时：**先** 扩展 `fields.yaml` / codegen，**再** 扩展 `postBaseDtoFromMap` 分发。

## 6. 风险

- 大范围改状态类型会引发 **大范围 diff**；必须按域切片、每切片 `flutter analyze` + 契约测试。  
- 部分页面仍依赖 `DataService` 遗留 Map：须在清单中单列 **deprecate_path**，避免与 Repository 双源。

## 7. P2 全量收敛：`target_dto: TBD` 与 DDD 边界附录

> 与「逐页强制」一致：每行须能回答 **限界上下文**、**聚合/一致性**、**读写 API（service.yaml）→ DTO → UI 消费点**。下列为 **登记用目标类型**；标「待 projection」的须先补 `contracts/metadata/.../projections/*.yaml` 再 `make codegen-app`。

### 7.1 chat（`messages/conversation`）

| 页面 / 挂靠面 | 限界上下文 | 主聚合 | 目标 wire DTO（codegen） | 主要 API / 说明 |
|---------------|------------|--------|---------------------------|-----------------|
| `chat_conversation_page` / `chat_detail_page` | chat | Conversation + Message | **`ChatMessageDto`**（`chat_message_client.yaml`） | `ListMessages` / `SyncMessages`；列表 State 为 `List<ChatMessageDto>`；气泡经 `toDisplayMap` |
| `chat_page` | chat | ChatInbox + Contact | `ChatInboxDto` / `ChatContactRowDto` | `ListInbox` / `ListContacts`；联系人 Tab 待收口 Map |
| `start_group_chat_page` | chat | Conversation + Member | `ChatInboxDto` / `ChatConversationMemberDto` / **圈子行待 Circle 投影** | 建群、选人；群组/圈子列表若属 circle 域须经 `CircleRepository` 类型 |
| `group_manage_page` | chat | Conversation（群规则） | **待 projection：`ChatGroupSettingsDto`**（或扩展现有 `getGroupSettings` 响应投影） | `GetGroupSettings` / `UpdateGroupSettings` |
| `chat_settings_page` | chat | ConversationMember + UserState | `ChatConversationMemberDto` + **会话元数据/设置待 DTO** | `ListMembers` / `GetConversation` 投影待对齐 |

### 7.2 content / discovery（`messages/content` / post projections）

| 页面 | 限界上下文 | 目标 DTO | 说明 |
|------|------------|----------|------|
| 详情 / 沉浸 / `media_post_card` | content | `PostBaseDto` 子类 | 分享/埋点若需 Map，仅允许 Repository 边界或一次性序列化 |
| `create_page` 等创作链 | content | **待 `DraftDocumentDto` / 分阶段 projection**（或现有 entry 模型逐步对齐 metadata） | 与 `service.yaml` 发布 API 字段一一对应后再改 UI State |

### 7.3 circle（`circle_dto.dart` 等）

| 页面 | 目标 DTO |
|------|----------|
| `circle_detail_page` / `circles_page` / `home_circles_hub_page` / `circle_edit_settings_page` / `circle_stats_page` | `CircleDto` / `CircleMemberDto` / `CircleSectionConfigDto` 等 **已有 hand+metadata 类型**；UI State 改为上述类型组合，禁止常驻 `Map` 表示圈子实体 |

### 7.4 user

| 页面 | 目标 DTO |
|------|----------|
| `other_profile_page` / `my_profile_page` / `edit_profile_page` | `UserProfileDto` |
| `persona_management_page` | `PersonaDto` |
| `sub_account_management_page` | **待 projection 或 `UserFullSnapshotDto` 子集** |
| `resonance_page` / `profile_stats_page` / `profile_comments_page` | **待读 models + metadata 增加 Search/Stats 视图投影** |

### 7.5 entity / search / rtc / assistant

| 域 | 页面 | 目标 DTO / 说明 |
|----|------|-----------------|
| entity | `homepage_*` | `lib/cloud/runtime/generated/entity/homepage_models.dart`（手写 DTO，字段对齐 `entity/homepage/fields.yaml`） |
| search | `global_search_page` / `search_network_results_page` | `search_contract.g.dart` 中 hits/sections 类型 |
| rtc | 通话各页 | `CallSessionDto` / rtc metadata 投影；选人页已混 chat DTO |
| assistant | 非 exempt 页 | 调云走 `AssistantRepository` + **assistant codegen**；引擎内部契约不替代云 DTO |

### 7.6 维护

- 本附录与 [`metadata_driven_ui_gap_inventory.yaml`](../../../../gates/metadata_driven_ui_gap_inventory.yaml) **同步迭代**：`target_dto` 列填 **类名**；`compliant` 须在 UI 主路径验证后更新。  
- 新增 projection 时同步更新 [`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) **P2** 列。

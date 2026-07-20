# 业务对象商用闭环：12 批推广规划（object-batch-rollout-plan）

> **目标**：以 Post / Comment / ProfileUpdateProposal 三个标本对象为范式，用 **12 个独立会话批次**（B0–B11）把 ContractGraph 当前登记的全部业务对象推进到商用闭环：清除所有 fake 与历史遗留、消除端云断点、按对象 kind 套用充分必要的并发/幂等模型、补齐三层测试与四环境证据、接通运维运营能力。对象总数只由当前 Graph 派生，不在规划中维护易漂移的手工计数。
> **真相源**：并发/幂等规则见 [design.md](../design.md)「按真实写入场景裁剪并发与幂等」；对象登记见各域 `quwoquan_service/contracts/metadata/{domain}/business_object_map.yaml`；readiness 阶梯见 `contracts/metadata/_schemas/readiness.schema.json` 与 `user/profile_update_proposal/readiness.yaml` 样板。
> **约束**：本文件只定义批次范围、标准与出口，不替代各对象所属 L1/L2/L3 的 spec/acceptance；批次执行发现规格缺口时先回补对应特性树文档。

## 1. 标本复核结论（2026-07-19 复核，B0 依据）

合格项（模型合理、无过度设计，可作范式）：

- 三标本覆盖三类聚合写入形态：**一次发布**（Post：`SubmitPostPublication` 稳定 publishIntentId + 唯一约束 + receipt）、**命名状态迁移**（Comment：删除/置顶/附件绑定，服务端内部 CAS + 有限重放 + no-op receipt）、**跨聚合检查点**（ProfileUpdateProposal：`confirmed -> applying -> applied|expired`，applying 阻断并发 Reject）。
- 调用方版本前置条件（`If-Match`）为 **4-operation 封闭清单**（`UpdateCircleGroup`、`UpdateCircleFile`、`UpdateExperimentRollout`、`UpdateServiceConfig`），由 `quwoquan_service/internal/metadata/graph/operation_concurrency_calibration__contract__local_contract_test.go` 锁定；公开请求不携带任何版本字段。
- 未引入通用 Saga、事件溯源、分布式事务、运行时对象注册或统一版本机制；OpenAPI 从类型化策略自动生成 `Idempotency-Key` / `If-Match` header。

缺口项（B0 收口，收口前不得宣称"标本四环境与运维运营全部具备"）：

- Post：6 个查询 operation（UpdateProfileInteractionState、GetAuthorImpact、ListAuthorImpactEvidence、GetCounters、GenerateArticleSummary、GetHelperRead）缺 telemetry/slo/commercial 合同，readiness 停在 modeled；缺 `readiness.yaml`；GWT3 缺 gamma_local UAT 运行制品。
- Comment：缺 `tests/mock.yaml`、`tests/e2e.yaml`；评论 UI 零行为埋点；缺 `readiness.yaml`。
- ProfileUpdateProposal：缺 `tests/` 三件套；无 alpha mock；无 user_acceptance；`readiness.yaml` 的 `user_acceptance`/`environments` 为空。
- 三对象共同：metadata 声明了对象级 metric/SLO，但 `quwoquan_ops/observability/monitoring/` 的告警与 dashboard 只有服务级通用规则，对象 metric 无消费者。

## 2. 统一标准（每批共用）

### 2.1 七步 DoD（每个对象）

| 步骤 | 要求 | 参照 |
|---|---|---|
| S1 metadata | `aggregate|entity.yaml`、`fields.yaml`、`errors.yaml`、`events.yaml`、`storage.yaml`、`service.yaml` + `tests/{contract,mock,e2e}.yaml` 三件套齐全；按对象 kind 套并发模板（见 2.2） | `contracts/metadata/content/post/`（唯一三件套齐全样板） |
| S2 codegen | `make verify-metadata` → `make codegen-contract-graph` → `python3 quwoquan_ops/cli/cloud_contract_handoff.py accept` → `make codegen-app`；OpenAPI 快照自动含幂等/并发 header | — |
| S3 服务端 packet | domain behavior + application facade（有限重试 + no-op receipt）+ 对象专属 Store（state/receipt/outbox 同事务原子提交）+ typed transport handler | `post_publication.go`、`comment_service.go`、`profile_update_proposal/facade.go` |
| S4 端侧 | pure contracts + alpha mock（物理隔离在 `quwoquan_cloud_mock`）+ thin Remote + typed Facet provider（≤10 方法）+ UI 消费 + 曝光/互动埋点（R20/R21） | notification/location 轨道：`app_message_facets_remote.dart` |
| S5 三层测试 | local_contract 覆盖 api_integration 验证的同一行为（Mock↔Remote 一体性）；api_integration 验真实存储 CAS/幂等/BOLA/outbox；user_acceptance 页面旅程 | `comment_aggregate__command_query__local_contract_test.go` 等 |
| S6 readiness | 每对象补 `readiness.yaml`（exact-path 实现 + 三层测试 + 环境 evidence）；阶段由 compiler 单调派生，禁止人工声明；目标 ≥ implemented，有环境制品达 commercial-ready | `user/profile_update_proposal/readiness.yaml` |
| S7 运维运营 | 全 operation telemetry/slo；对象核心 metric 被告警/dashboard 消费；`commercial.status` 翻 ready；CR 记录 | B0 落地的告警覆盖 verify 脚本 |

### 2.2 并发/幂等模板（按对象 kind，禁止跨类混用）

- **一次创建/发布**：稳定 intent（客户端生成、不可变）+ 存储唯一约束 + 永久业务幂等（聚合自身承载；command receipt 为 24h 幂等窗口）；同 intent 复用于另一草稿/载体返回 idempotency conflict。
- **命名状态迁移 / set**：服务端加载当前 version + 内部 CAS + ≤3 次重放；目标状态已满足时持久化 no-op receipt（不递增版本、不产伪事件）；调用方不提交版本。
- **多人快照覆盖（If-Match）**：封闭清单 4 个 operation，**任何批次不得新增**；如确有新场景，先按 design.md 决策流程扩清单并更新校准合同测试。
- **append-only fact**：typed append + 唯一 dedupe key；无 update/delete；不因运营需要加公开 operation。
- **projection**：只由 projector 写入，按 source 单调 version/sequence；可重建；无消费方的投影先决策砍/延后。
- **external reference**：只读查询，不持有并发状态。
- **runtime session**：逐连接 lease + fencing token；外部 webhook 先归一化为对象专属 receipt fact 再事件投递，禁止把 webhook 声明成 session command。
- **跨聚合工作流**：对象专属最小持久化检查点（如 applying），不引入通用 Saga。

### 2.3 清除类标准（每批强制，"清 fake 与历史遗留"）

1. 批内域在 production `lib/` 内的 Mock/Fake/prototype 数据与类：迁 `packages/quwoquan_cloud_mock`（经 seed manifest 生成 typed bundle）或直接删除；同步删除运行时 Mock/Remote 切换分支。
2. `AppDataSourceMode`：批内域引用清零（棘轮只减不增）；B11 收尾时删除本体并把棘轮基线归零。
3. 空 catch / 注释化 best-effort catch：改结构化（`RuntimeFailure` + logger/telemetry），或删除该分支。
4. TODO/FIXME/@Deprecated：逐条三选一——接通已有后端能力 / 删除 / 经用户确认登记 backlog；不允许原样保留。
5. 硬编码 path、错误码、surfaceId 字符串：改 generated 常量（metadata-first）。
6. 聚合 Repository（>10 方法）：拆对象级 `*CommandWriter/*Query` Facet（R02）；消费者原子切换后删除旧接口，不留双轨。
7. 服务端 fake：内存 map 冒充持久化、`handleNotImplemented` 兜底 dispatch、端侧合成数据伪装 Remote 成功——一律替换为真实实现或显式砍掉（metadata 同步）。

### 2.4 不过度设计三问（每个新增抽象/实现前自检）

1. 是否已有可复用抽象？有则复用。
2. 是否与现有抽象重叠？重叠先重构统一。
3. 删掉后系统是否照常运行？照常说明不该建。

补充裁剪原则：fact 不加公开 operation；无消费方的投影/写模型先向用户提"实现 or V1 显式砍"决策，默认砍；错误处理只在系统边界校验；不为假想的未来需求建 flag/shim。

### 2.5 批次级验收

- 本 story `acceptance.yaml` 的 `execution.local_gate` 全部命令通过 + `make gate` 对应 scope。
- Exit Review 七项：规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁、剩余风险。
- 四文档同步：各对象 `readiness.yaml`、所属特性树 `acceptance.yaml`（诚实 status）、`specs/changelog/CR-*.yaml`、`docs/outstanding_risks_backlog.md`（新风险经用户确认）。
- 环境证据不足（如凭据受限、gamma 制品未取得）时诚实标 partial 并写明缺口，禁止放宽测试或绕过门禁。

### 2.6 批次通用门禁命令

```bash
# 契约链（quwoquan_service 目录）
make verify-metadata && make codegen-contract-graph && python3 ../quwoquan_ops/cli/cloud_contract_handoff.py accept && make codegen-app
# 端侧一致性（仓库根目录）
make verify-app-contract-handoff && make verify-app-generated-manifest && make verify-app-cloud-package-boundaries && make verify-app-mock-isolation && make verify-test-specs
# 运行时错误单轨
dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
# 批内对象定向测试（go test / flutter test，按批次节列出）
# 收尾全量
make gate
```

## 3. 一键复制会话指令（模板）

每批指令在 §5 各批次节末尾给出，均为自包含文本，可直接复制到新会话执行。模板结构：

```text
执行业务对象推广批次 B<N>（<批次名>）。
范围对象：<domain/object 清单>。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B<N> 节
3. .cursor/rules/01-arch-constraints.mdc §2.5 对象 operation 端云对齐检查清单
标本参照代码：
- quwoquan_service/services/content-service/internal/application/post/post_publication.go（一次发布）
- quwoquan_service/services/content-service/internal/application/comment/comment_service.go（命名迁移 + no-op receipt）
- quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal/facade.go（跨聚合检查点）
- 端侧轨道：quwoquan_app/lib/cloud/services/notification/remote/app_message_facets_remote.dart + quwoquan_app/lib/ui/content/entry/providers/post_publication_intent_queue_provider.dart
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；B<N> 节「决策项」逐条先向用户确认再实施。
- 逐对象走 §2.1 七步 DoD；完成 B<N> 节全部「清除项」与「补齐断点」。
- 禁止：新增 If-Match operation、通用 Saga/事件溯源、聚合 Repository、lib 内 mock、协议版本信封、绕过 codegen 手改产物。
完成后：跑 §2.6 通用门禁 + B<N> 节定向测试；更新各对象 readiness.yaml、所属 acceptance.yaml、CR、backlog；输出 Exit Review 七项。
```

## 4. 业务对象与批次归属总表

kind 缩写：AR=aggregate_root，OE=owned_entity，F=append_only_fact，P=projection，ER=external_reference，RS=runtime_session。OE 跟随 aggregate_owner、P 跟随 source 宿主进入同一批次。

| 域 | 对象（目录名） | kind | 批次 |
|---|---|---|---|
| content | post | AR | B0 |
| content | comment | AR | B0 |
| user | profile_update_proposal | AR | B0 |
| user | user_profile（UserAccount） | AR | B1 |
| user | account_session | AR | B1 |
| user | authentication_challenge | AR | B1 |
| user | credential_binding | AR | B1 |
| user | device_registration | AR | B1 |
| user | user_settings | AR | B1 |
| user | persona | AR | B1 |
| content | content_reaction | AR | B2 |
| content | media_asset | AR | B2 |
| content | media_upload_session | AR | B2 |
| content | media_original_access_fact | F | B2 |
| content | outbound_share_fact | F | B2 |
| content | report | AR | B2 |
| content | post_moderation_case | AR | B2 |
| content | deleted_post_tombstone | F | B2 |
| content | profile_interaction_activity_view | P | B2 |
| content | profile_interaction_read_fact | F | B2 |
| user | persona_relationship | AR | B3 |
| user | relationship_direction | OE | B3 |
| user | subject_follow | AR | B3 |
| user | greeting_request | AR | B3 |
| user | invite_record | AR | B3 |
| user | contact_discovery | AR | B3 |
| user | followed_subject_visit_state | AR | B3 |
| user | following_subject | P | B3 |
| user | creator_runtime_profile | P | B3 |
| user | user_life_item | P | B3 |
| user | user_work | P | B3 |
| social(circle) | circle | AR | B4 |
| social(circle) | circle_section_config | OE | B4 |
| social(circle) | circle_membership | AR | B4 |
| social(circle) | circle_group | AR | B4 |
| social(circle) | circle_group_membership | AR | B4 |
| social(circle) | circle_file | AR | B4 |
| social(circle) | circle_post_placement | AR | B4 |
| social(circle) | circle_behavior_fact | F | B4 |
| social(circle) | circle_search_item_view | P | B4 |
| messages(chat) | conversation | AR | B5 |
| messages(chat) | conversation_membership | AR | B5 |
| messages(chat) | message | AR | B5 |
| messages(chat) | conversation_user_state | AR | B5 |
| messages(chat) | message_receipt_fact | F | B5 |
| messages(chat) | chat_inbox_view | P | B5 |
| messages(chat) | conversation_search_item_view | P | B5 |
| messages(chat) | message_search_item_view | P | B5 |
| entity | homepage | AR | B6 |
| entity | homepage_claim_request | AR | B6 |
| entity | homepage_review | AR | B6 |
| entity | homepage_status_report | AR | B6 |
| entity | homepage_search_item_view | P | B6 |
| search | query（SearchQuery） | F | B7 |
| search | recent_search_state | AR | B7 |
| search | search_feedback_fact | F | B7 |
| search | search_recommendation_signal_fact | F | B7 |
| search | search_index_view | P | B7 |
| tag | tag（TagNodeView） | P | B7 |
| tag | tag_feedback | F | B7 |
| tag | taxonomy_release | AR | B7 |
| tag | object_tag_index_view | P | B7 |
| assistant | assistant_conversation | AR | B8 |
| assistant | assistant_run | AR | B8 |
| assistant | skill_subscription | AR | B8 |
| assistant | skill_consent | AR | B8 |
| assistant | assistant_turn_view | P | B8 |
| assistant | assistant_interaction_event | F | B8 |
| assistant | assistant_scorecard_fact | F | B8 |
| recommendation | model_release | AR | B9 |
| recommendation | recommendation_intersection_visit_state | AR | B9 |
| recommendation | recommendation_exposure_fact | F | B9 |
| recommendation | recommendation_feedback_fact | F | B9 |
| ops | experiment | AR | B9 |
| ops | experiment_assignment_fact | F | B9 |
| ops | event_record | F | B9 |
| ops | visit_record | F | B9 |
| ops | config_layer | AR | B9 |
| ops | config_entry | OE | B9 |
| realtime | connection | RS | B10 |
| realtime | channel_ingress_receipt | F | B10 |
| realtime | presence_view | P | B10 |
| rtc | call_session | AR | B10 |
| rtc | call_participant | OE | B10 |
| rtc | call_recording | AR | B10 |
| integration | external_interaction | AR | B11 |
| integration | external_interaction_attempt_fact | F | B11 |
| integration | external_interaction_dead_letter_fact | F | B11 |
| integration | location | ER | B11 |
| notification | notification | AR | B11 |
| notification | notification_delivery_job | AR | B11 |

批次依赖：B0 先行（模板与基建冻结）；B1 是 api_integration/UAT actor 前提；B5 的实时推送依赖 B10；B11 的推送 provider 供 B5/B10 消费；B6–B9 与主线批次可并行（不同域独立会话）。

## 5. 批次详情

### B0 标本收口 + 推广基建（3 对象）

范围：`content/post`、`content/comment`、`user/profile_update_proposal`。

补齐项：

- Post：为 6 个查询 operation（UpdateProfileInteractionState、GetAuthorImpact、ListAuthorImpactEvidence、GetCounters、GenerateArticleSummary、GetHelperRead）补 telemetry/slo/commercial 合同；新建 `contracts/metadata/content/post/readiness.yaml`；取得 gamma_local 崩溃恢复 UAT 运行制品（`.qwq_output/env/gamma/runs/**`）后翻 GWT3 状态。
- Comment：补 `tests/mock.yaml`、`tests/e2e.yaml`；`lib/ui/content/comments/` 补曝光/互动埋点；新建 `readiness.yaml`。
- Proposal：补 `tests/{contract,mock,e2e}.yaml`；新建 `packages/quwoquan_cloud_mock/lib/src/user/` alpha mock adapter；补 proposal 专属 user_acceptance；review sheet/edit_profile 埋点；`readiness.yaml` 补 `user_acceptance`/`environments` 段。

推广基建（防 88 个对象复制断链）：

- 新增 verify 脚本：`commercial.status: ready` 的 operation，其 telemetry metric 必须被 `quwoquan_ops/observability/monitoring/` 的告警或 dashboard 消费，否则 GATE_BLOCK；为三标本核心 metric（`content_post_publication_submit`、`content_comment_*`、`user_profile_proposal_command`）补 Prometheus 规则。
- mock 隔离门禁扫描范围扩至 `lib/cloud/**`（当前 `verify_ui_mock_isolation.py` 只扫 `lib/ui|app|core`，1136 行 `content_mock_data.dart` 等长期漏扫）。
- 文字校准：acceptance 中"永久 receipt"统一为"聚合承载永久幂等语义 + command receipt 24h 窗口"。

```text
执行业务对象推广批次 B0（标本收口 + 推广基建）。
范围对象：content/post、content/comment、user/profile_update_proposal。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B0 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection。
- 完成 B0 节全部补齐项与推广基建三件事（告警覆盖 verify 脚本 + Prometheus 规则、mock 隔离扫描扩 lib/cloud、receipt 口径校准）。
- 三对象各补/完善 readiness.yaml，目标 readiness ≥ implemented；gamma_local 制品取得后翻 commercial-ready，取不到则诚实 partial 并写明。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 object-batch-rollout-plan.md §2.6 通用门禁 + story acceptance execution.local_gate；更新 acceptance/CR/backlog；输出 Exit Review 七项。
```

### B1 身份账号（7 对象，B0 后串行优先）——已执行（2026-07-20，双会话协作收口）

执行结果（详见 CR-20260719-120 B1 entry）：

- metadata：6 对象 errors.yaml 按归属拆分（新增 challenge_consumed、settings_version_conflict）；RegisterDevice 显式 deferred（登录内 registrar 落库承载，pushToken 改密文+fingerprint 双列）；26 命令 op client_contract + pure contracts typed 契约 5 文件；PersonaManagementItemView 与 Persona 实体字段单轨对齐；ui_surfaces 挂载 login/appShell/settings/settingsDarkMode/profilePersonas/profileEdit；readiness.yaml×7。
- 服务端：AccountSession（per-session hash + rotation lineage 重放吊销 + 事务 outbox）、AuthenticationChallenge（原子一次性消费 + completion fingerprint 重放）、UserSettings（20 字段单聚合 version CAS + no-op receipt，8 端点接对象 facade，旧 SettingService 退役，身份 operation.Context 单轨）、CredentialBinding（DB 唯一约束冲突映射 + version + outbox）四 packet；migration 023/024/027。
- 端侧：persona 6 命令切 typed facet（UserRepository 收敛为读投影）；settings 读投影按 slice 拆三 view + getCallSettings；设置中枢补「通知与提醒」「通话与铃声」端到端区块（乐观更新+回滚）；prototype_mock_data 孤儿删除。
- 运维：quwoquan_l2_auth_login 组补 OTP 失败率/设置写失败率/persona 命令失败率三条对象级告警。
- 诚实注记：R-AUTH-001 社交登录 op 保持 blocked（wechat/alipay/qq/one-tap 无 prod 凭据）；user_settings UAT journey 与 gamma user_api_contract_runner 待补；user_profile 20 查询 op 的 per-op commercial 翻牌待三层测试全绿后收口。

范围：`user/user_profile`、`user/account_session`、`user/authentication_challenge`、`user/credential_binding`、`user/device_registration`、`user/user_settings`、`user/persona`。

清除项：

- `quwoquan_app/lib/cloud/services/user/user_profile_repository*.dart`：34 方法聚合 Repository 按消费场景拆对象级 Facet（profile 快照/编辑、settings、session、persona 等），消费者原子切换后删除旧接口。
- user 域 production `lib/` 内 6 个 Mock 文件迁 `quwoquan_cloud_mock` 或删除；`AppDataSourceMode` 的 user 域引用清零。
- 3 处硬编码 path（含 `/users/` 脏埋点）、6 处 `@Deprecated` 清理；recent search 相关代码不动（归 B7）。

补齐断点：

- user_settings：端侧 DTO 缺 9 个字段，与 `contracts/metadata/user/user_settings/fields.yaml` 对齐（先核 metadata 是否为真相，再改端侧）。

模型要点：session 登录/登出、challenge 验证/消费为命名状态迁移（服务端 CAS + 一次性消费语义）；credential_binding 唯一约束防重绑；user_settings 更新为服务端内部 CAS（aggregate.yaml 已声明）。

验收注记：beta/gamma 真实凭据受 backlog R-AUTH-001 制约，四环境证据允许诚实 partial，本地/alpha 证据必须完整。

```text
执行业务对象推广批次 B1（身份账号）。
范围对象：user/user_profile、user/account_session、user/authentication_challenge、user/credential_binding、user/device_registration、user/user_settings、user/persona。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B1 节
3. .cursor/rules/01-arch-constraints.mdc §2.5；docs/outstanding_risks_backlog.md 的 R-AUTH-001
标本参照代码：quwoquan_service/services/content-service/internal/application/comment/comment_service.go（命名迁移 + no-op receipt）、quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal/facade.go 及端侧 typed Facet/alpha mock/三层测试。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；无决策项，但发现规格缺口先回补特性树。
- 完成 B1 节清除项（UserProfileRepository 拆分、6 个 Mock 迁移、AppDataSourceMode user 引用清零、硬编码 path 与 @Deprecated 清理）与断点补齐（user_settings 9 字段对齐）。
- 逐对象走七步 DoD（含 tests 三件套、readiness.yaml、埋点、telemetry/slo、告警覆盖）。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 object-batch-rollout-plan.md §2.6 通用门禁 + user 域定向 go test/flutter test；beta/gamma 凭据受限处诚实 partial；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B2 内容与媒体（10 对象）——已执行、真实性复核未准出（2026-07-19）

范围：`content/content_reaction`、`content/media_asset`、`content/media_upload_session`、`content/media_original_access_fact`、`content/outbound_share_fact`、`content/report`、`content/post_moderation_case`、`content/deleted_post_tombstone`、`content/profile_interaction_activity_view`、`content/profile_interaction_read_fact`。`PostSearchItemView` 已裁决为 canonical Search response 的 typed content Slice，不再作为独立业务对象。

清除项：

- `lib/cloud/services/content/mock/content_mock_data.dart`（1136 行）+ `mock/generated/home_showcase_core_fixture.g.dart` 迁 `quwoquan_cloud_mock`；删除 `MockContentRepository` 三个 part 文件；`app_providers_content_facets.dart` 的 `_contentFacetsProvider` 改 Remote-only 装配。
- `discovery_wire_lookup.dart` 中 `mockDiscovery*WireFallback`/`prototypeDiscoveryWireRowForMock` 死函数删除。
- 服务端 `content_handler_operations.go` 的 `handleNotImplemented` 兜底 dispatch（generated 表标 not-implemented、手写 switch 兜转真实 handler 的双轨）回归 codegen 单轨。
- `lib/components/content/media_post_card.dart` 12 处 TODO：举报、查看原图接已有后端（`RemoteContentReportAdapter`、`RequestOriginalImageAccess`）；其余逐条三选一。
- content 域约 20 处空 catch（`create_page_state.dart`、`create_draft_local_storage.dart`、`video_editor_page_state.dart` 等）结构化。

补齐断点：

- 举报→审核闭环：moderation service 装配进 `cmd/api/main.go`、report outbox 接 `moderation-projection` consumer、4 条 internal 路由接通、补 api_integration。
- deleted_post_tombstone：内存 map（`post_service.go:45`）替换为 Mongo 集合 + TTL（storage.yaml 已声明）；统一 404/410 语义（service.yaml 与 handler 测试当前矛盾）。
- BehaviorEvent 的 `pageVisitId` 与 pageflip motion 字段端云对齐：在 `behaviors.yaml` + `BehaviorEventInput` 声明，或端侧停发（当前服务端静默丢弃）。

模型要点：reaction 为 set/unset 命名迁移（服务端 CAS + no-op receipt）；media_original_access/outbound_share/tombstone 三个 fact 用 dedupe key；moderation 为命名状态迁移；upload session 生命周期 init/complete/abort 已闭环，仅补合同与证据。

```text
执行业务对象推广批次 B2（内容与媒体）。
范围对象：content/content_reaction、content/media_asset、content/media_upload_session、content/media_original_access_fact、content/outbound_share_fact、content/report、content/post_moderation_case、content/deleted_post_tombstone、content/profile_interaction_activity_view、content/profile_interaction_read_fact。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B2 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：quwoquan_service/services/content-service/internal/application/{post/post_publication.go,comment/comment_service.go} 及端侧 reaction/media/report 已有 typed Facet（lib/cloud/services/content/remote/、lib/cloud/remote/content/media/）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；media_post_card 的 TODO 三选一清单先向用户确认。
- 完成 B2 节清除项（content mock 迁移与 Remote-only 装配、死函数删除、handleNotImplemented 双轨清除、TODO 与空 catch 治理）与断点补齐（举报→审核闭环、tombstone 落 Mongo、BehaviorEvent 字段对齐）。
- 逐对象走七步 DoD；三个 fact 与两个 projection 按对应模板收口，不加公开 operation。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + content 域定向测试（含 moderation 新增 api_integration）；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

执行结果（2026-07-19，决策随计划批准确认）：

- **metadata 收口**：post 6 个裸 operation（UpdateProfileInteractionState/GetAuthorImpact/ListAuthorImpactEvidence/GetCounters/GenerateArticleSummary/GetHelperRead）补全套合同，前 4 个翻 ready，后 2 个诚实 blocked（缺测试证据 gap）；errors.yaml 按对象拆分为 10 份（comment 双源漂移消除，Go/Dart codegen 与两个 parity 门禁改为固定文件列表合并，错误码全集为旧集超集 +2 找回漂移码）；tombstone entity 补 business_rules/lifecycle + BOM refs 回填（outbound_share 同步）；behaviors.yaml 契约单轨（dwell 唯一键 `duration` 秒、位置唯一键 `position`、删除 feedPosition/dwellMs 声明；补 reasonVersion/recallPath/contentVertical/supplySource 归因字段；声明 entity_page_view；shareTarget/join_circle 语义注记）；tests 三件套 10 对象补齐；reaction 3 处失效 go_func 改绑真实测试、post 幽灵 MarkIntersectionsVisited 场景删除、profile_interaction_activity_view 双源登记统一（wire 投影 source_entities 修正）、media/outbound_share defaults gap 与 operation 级对齐。
- **服务端**：moderation 全量装配（main.go Mongo store + facades + relay + healthz）；举报→审核闭环（report outbox 第二 consumer `content-report-moderation-projection` 经 ReportCaseOpener 幂等开 case，OpenPostModerationCase 增加 post-revision 一次创建语义归并并发/多举报）；codegen 模板补 12 个缺失 dispatch 分支（含 5 个 moderation 新 handler），`handleNotImplemented` 手写 switch 兜底删除（双轨归一）；tombstone 落 Mongo `deleted_post_tombstones`（DeletePost 同事务追加、TTL 30 天、GetPost 保留期内 410 content_deleted、TTL 后 404，重启存活由测试锁定）；no-op receipt 补齐（UpdateMediaAssetAccessPolicy 目标 policy 已满足、report BeginReview/Resolve 目标状态已满足，Mongo/PG/testsupport 三实现）；behavior 双读键收敛（`postId/type/dwellMs/feedPosition` 4 个旧键删除，`TestBehaviorBatchCanonicalWire` 改为单轨正例 + 旧键 400 负例）。
- **端侧**：content Remote-only 改造（MockContentRepository 三 part + ContentMockData + discovery_wire_lookup + MockFootprintRepository 物理迁至 `test/support/cloud_services/content/`；runners/alpha 新增 AlphaContentRepository/AlphaFootprintRepository fixture 回放实现 + 9 个 provider override；`_contentFacetsProvider`/`_contentPostReaderProvider`/`contentPostSearchRepositoryProvider`/`footprintRepositoryProvider` 全部 Remote-only 守卫；38 个测试文件 import 迁移；fixture 门禁改址）；MediaPostCard 体系（media/image/video_post_card 三文件 + 2 widget 测试 + TestKeys.videoPostCard）整体下线；image_viewer 打赏/私信/复制链接假 toast 入口删除、「查看原图」接真实 requestOriginalAccess（授权 URL 重载当前图 + 结构化错误文案）、时间字面量语义化；空 catch 数据丢失点治理（create_draft_local_storage 4 处 decode 损坏侧位保留 `create_drafts_corrupt:*` + 损坏计数 + 结构化日志；publish_circle_services 吞错已由先前批次修复确认）。
- **可观测**：举报三 surface（沉浸浏览/首页 feed/用户主页）补 `product_action` 漏斗埋点（journey=content_report，success/failure + failReasonCode + durationMs）；媒体上传协调器补 `operation_result` + `performance_sample`（operationId=content.media_upload_session.UploadMedia，5 个构造点注入 recorder，发布/评论附件/圈子存储/聊天全链生效）；Prometheus 新增 `quwoquan_l2_content_objects` 告警组（发布/点赞/行为/上传/举报错误率 + 读主链 P95）；新增 `verify_content_object_alert_coverage.py` 门禁（6 条核心主链告警覆盖）并挂入 gate_repo.sh。
- **readiness / 门禁**：10 对象 readiness.yaml 全部登记且路径经存在性校验；`verify_ui_mock_isolation.py` 扫描范围扩 `lib/cloud`（content 域零违规；circle/entity/rtc/user/chat 存量 8 条进 allowlist 棘轮基线，注记归属批次 B3–B9 清零）。
- **commercial 翻转**：moderation 5 op、media transport 3 op（RecordMediaProcessingResult/UpdateMediaAssetAccessPolicy/GetOwnedMediaAsset）翻 ready；`*_GAMMA_UAT` 类 gap（media 8 op、outbound_share 1 op）本批未取得 gamma_local 制品，保持 blocked 并已把 block_reason 与 operation 级实现现状对齐。
- **测试证据**：content-service internal + local_contract 全绿；api_integration 全量绿（含新增 TestReportOutboxOpensModerationCase / TestModerationDecisionGatesPublicationEligibility / TestGetPostTombstoneReturnsGone）；端侧 content/create/media 契约测试 368 通过；verify-metadata / codegen 链幂等 / single-track / recovery-alignment / alert-coverage / mock-isolation / ratchet 全绿。
- **遗留**：GenerateArticleSummary/GetHelperRead 缺测试证据保持 blocked；gamma 环境级证据随环境批次补录；并行会话的 user/invite_record parity 列表同步与 entity 枚举重生成属其收尾职责，不计本批。

真实性复核（2026-07-19）：

- 上述“执行结果”只证明首轮实现落地，不等于商用闭环。以同一稳定 ContractGraph 重算后，B2 为 **8 个 implemented、2 个 contract-ready、0 个 commercial-ready**；10 份 readiness 均无完整环境证据。
- 首轮存在 `PostSearchItemView` 与全局 Search 双查询真相源、`ProfileInteractionActivityView` 未由事件真实物化、Report→Moderation 吞错及 Moderation 决策未回写 Post 等问题；真实性收口必须以删除双轨、真实投影和 durable lifecycle consumer 的运行证据关闭这些缺口。
- B2 已重新打开，按“B2 真实性与商用成熟度收口”完成对象身份、投影/检查点、页面、三层测试、对象级观测和四环境证据后，方可改为 commercial-ready；在此之前不得启动依赖其商用完成声明的下一批准出。

### B3 关系与个人投影（11 对象）——已执行（2026-07-19）

范围：`user/persona_relationship`（含 `relationship_direction`）、`user/subject_follow`、`user/greeting_request`、`user/invite_record`、`user/contact_discovery`、`user/followed_subject_visit_state`、`user/following_subject`、`user/creator_runtime_profile`、`user/user_life_item`、`user/user_work`。

补齐断点：

- persona_relationship 字段级断点：云侧下发 `isBlocked/isBlockedBy`、端侧期望 `isFollowing/isFollowedBy/isMutual`——先在 `fields.yaml` 冻结 wire 真相，再同步 Go/Dart 两端。
- subject_follow、followed_subject_visit_state、following_subject：契约有、云侧零实现，补完整服务端 packet（store/outbox/reader/transport）与端侧消费。

决策项（先向用户确认）：

- creator_runtime_profile、user_life_item、user_work 三个空 routes 投影：实现 or V1 显式砍（从 metadata 移除或标注 deferred）；默认建议砍，避免过度设计。

模型要点：follow/unfollow 为关系 set/unset（服务端内部 CAS + idempotency receipt，aggregate.yaml 已声明）；visit_state 单调推进（重放不回退）；greeting/invite 为命名状态迁移。

执行结果（2026-07-19，决策已用户拍板）：

- **决策落地**：SubjectFollow 收敛为主页/圈子/地点关注唯一真相源，`entity.FollowHomepage/UnfollowHomepage` 原子退役（metadata route、Go handler/service、App 调用点同批切换）；`user_work`/`user_life_item` 双砍（route/store/service/端侧死链全删，entity.yaml 标 deferred）；`invite_record` 彻底删除（metadata 目录、Go packet、DB drop migration、端侧断言），对象总数 91→90。
- **零实现补齐**：subject_follow PG 聚合 + receipt + outbox + relay；followed_subject_visit_state Mongo 单调水位 + clientRequestId 重放；following_subject Mongo 投影（消费 PersonaFollowStateChanged/SubjectFollowStateChanged，circle 事件随 B4 接入）+ enrich reader；entity-service 增加 Redis Stream consumer 维护 homepage follower 投影。
- **存量收口**：greeting receipt/outbox 事务化（替换直发吞错）+ 20/24h 限流；contact TTL 72h 物理清理 ticker + 2 事件；persona_relationship capability 四方对齐（16 字段）+ `USER.RELATIONSHIP.follow_blocked` 错误码；`relationship_normalized_wire` 退役，端侧改消费 `RelationshipViewWire` + view model 派生布尔。
- **端侧**：陌生人私信按能力位分流到打招呼破冰（composer + pending 提示）；关注/取关/打招呼/关注频道点击埋点接入 `product_action`；`user_profile_repository_remote` 17 处裸 `throw Exception` 全部切 `CloudErrorMapper`；Greeting/Block/RelationshipCapability 三仓库 extends→implements；discovery 假关注用户与 prototype 生活假数据删除。
- **B3.5 页面商用收口**：新增拉黑管理与打招呼收发箱两页，拉黑/打招呼/通讯录三条旅程均可逆且错误结构化；拉黑读写切对象级 generated Facet，关注状态收敛到 UserRelationshipState + 持久 outbox，删除 discovery.followingUsers 与 user_profile_mock_data；profile shell 分片回到 1000 行内，页面矩阵/对象契约/UAT 证据补齐。
- **遗留**（B4+ 或环境批次）：greeting `sender_realname_required`/`minor_restricted` 逻辑随 safetyGate 基建接入；following_subject 的 circle 事件源与内容变化未读信号随 B4/内容事件批次接入；UserProfileRepository 聚合仓库的对象级 Facet 全量拆分与 AppDataSourceMode 退役随 B1 收尾复核；gamma 环境级证据待环境批次统一补录。

```text
执行业务对象推广批次 B3（关系与个人投影）。
范围对象：user/persona_relationship（含 relationship_direction）、user/subject_follow、user/greeting_request、user/invite_record、user/contact_discovery、user/followed_subject_visit_state、user/following_subject、user/creator_runtime_profile、user/user_life_item、user/user_work。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B3 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：quwoquan_service/services/content-service/internal/application/comment/comment_service.go（set/unset + no-op receipt 范式）及 user 域既有 PG store 形态。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；三个空 routes 投影（creator_runtime_profile/user_life_item/user_work）的「实现 or V1 砍」决策先向用户确认。
- 完成断点补齐：persona_relationship 字段真相冻结与两端对齐；subject_follow/followed_subject_visit_state/following_subject 云侧 packet 从零补齐。
- 逐对象走七步 DoD（含 tests 三件套、readiness.yaml、埋点、告警覆盖）。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + user 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B4 圈子（9 对象）

范围：`social/circle`（含 `circle_section_config`）、`social/circle_membership`、`social/circle_group`、`social/circle_group_membership`、`social/circle_file`、`social/circle_post_placement`、`social/circle_behavior_fact`、`social/circle_search_item_view`。

执行结果（2026-07-19）：9 对象已按对象 packet 收口；Circle 本体命令使用服务端 CAS + actor-scoped receipt + 事务 outbox，placement 展示位改 outbox projector，40 个 operation 商用合同、tests 三件套、readiness 与对象级告警完成。完整证据见 CR-120 B4 entry。

清除项：

- circle mock（`lib/cloud/services/circle/mock/circle_mock_data.dart` 及其对 `lib/core/mock/prototype_mock_data.dart` 的引用）迁移/删除，`prototype_mock_data.dart` 同步瘦身；circle 域 `AppDataSourceMode` 引用清零。
- circle 页面（`lib/ui/circle/`）行为埋点补齐（R20）。

补齐断点：

- ~~`MediaAssetDeleted` 跨域事件 consumer 落地~~（2026-07-19 执行裁决修正：content 侧不存在该事件生产者，实现消费者属过度设计；已删除 `business_object_map.yaml` 的悬空 `event_consumers` 声明，CircleFile↔MediaAsset 引用完整性由既有 tombstone 关系承载）。
- 展示位（pin/feature）投影断点（2026-07-19 落地）：删除 `/circles/{id}/feed/{postId}/pin|feature` 野路由，placement outbox 新增 feed presentation projector 回写 posts 读模型，展示位真相源唯一在 CirclePostPlacement 聚合。

模型要点：`UpdateCircleGroup`/`UpdateCircleFile` 是全仓仅有的 If-Match 第三类参照实现——本批复核其实现与 `operation_guard` 校验链后确认为第三类模板；membership/group_membership 申请/审批/移除为命名状态迁移；placement 置顶/精华为 set 操作；Circle 本体 Update/Archive/UpdateSections 为第二类命名迁移（服务端内部 CAS，公开请求不携带调用方版本字段）。

```text
执行业务对象推广批次 B4（圈子）。
范围对象：social/circle（含 circle_section_config）、social/circle_membership、social/circle_group、social/circle_group_membership、social/circle_file、social/circle_post_placement、social/circle_behavior_fact、social/circle_search_item_view。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B4 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：comment_service.go（命名迁移）+ circle-service 内 UpdateCircleGroup/UpdateCircleFile 的 If-Match 实现（第三类唯一参照，复核后固化为模板）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；无新增决策项。
- 完成清除项（circle mock 迁移、prototype_mock_data 瘦身、AppDataSourceMode circle 引用清零、circle 页面埋点）与断点补齐（MediaAssetDeleted consumer 落地 + api_integration）。
- 逐对象走七步 DoD；If-Match 保持封闭清单不扩。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + circle 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B5 消息（8 对象）

范围：`messages/conversation`、`messages/conversation_membership`、`messages/message`、`messages/conversation_user_state`、`messages/message_receipt_fact`、`messages/chat_inbox_view`、`messages/conversation_search_item_view`、`messages/message_search_item_view`。

清除项：

- `ChatRepository`（36 方法）拆对象级 Facet；4 处 Remote 端侧合成数据伪实现清除（端侧不得为失败/缺失合成成功数据）；chat mock 迁 `quwoquan_cloud_mock`。
- 7 处注释化空 catch 结构化；chat 页面（10 页）零埋点补齐（R20）。

补齐断点：

- chat-service 966 行单体 store 按对象拆 packet（conversation/membership/message/user_state 各自 Store + outbox）。
- 发送 → outbox → inbox 投影 → 已读回执链闭环并补 api_integration。

验收注记：实时推送依赖 B10 realtime-gateway；本批保证拉取/轮询路径完整可用并在 acceptance 诚实标注实时缺口；B10 完成后回归实时 E2E。

B5 执行结果（2026-07-19）：

- 裁决落地：SendMessage 幂等单轨（Idempotency-Key==clientMsgId，metadata 描述冻结）；
  `SearchConversations`/`SearchMessages`/`SearchContacts` 三 operation 与两个 ES 搜索
  投影对象删除（本地 sqlite 检索单轨，对象数 8→6）；联系人 Tab 圈子行正名调用
  circle `ListCircles` 真实契约头；message_receipt_fact 不造伪 operation——
  `append_only_fact` 零公开 op 纳入 graph contract-ready 豁免（服务端内生事实的
  范式级修正）；inbox 投影以 `conversation_user_states` join `conversations` 为
  物理载体，不建第二份 `rm_chat_inbox` 复制集合（chat_inbox.yaml 口径已同步）。
- metadata：30 operation 全套商用合同；新增 `CHAT.USER.group_governance_forbidden`；
  conversation 补 receipts/outbox/`chat_aggregate_outbox_sequences`/
  `chat_projection_checkpoints` 集合；12 事件 channel 统一 transactional_outbox；
  message/membership/user_state 补 tests 三件套；4 聚合 readiness.yaml 达
  implemented（fact/projection 两对象待 readiness 机制支持无目录对象，诚实停
  contract-ready）。
- 服务端：单体 store 拆 4 对象文件 + 共享 `MongoAggregateCommandStore`
  （actor-scoped 幂等回执、digest 冲突、no-op receipt、事务 outbox）；10 处
  goroutine 直发清零（九命令事务化 + RecallMessage 入 Message outbox，roster
  debounce 旁路删除）；`AggregateOutboxRelay` 泛化三聚合投递；`InboxProjector`
  消费 MessageSent 原子推进未读（sender 不计数、mention 计数、checkpoint 可
  重放）；MarkAsRead 已读水位单调 no-op；`IncrementUnread` 死代码删除。
- 端侧：六对象 Facet provider 拆分（production 组合根 Remote-only，
  `chatRepositoryCompositionProvider` 单点 override）；AppDataSourceMode chat
  分支清零；`ChatSendOutbox` 统一持久化待发队列（文本+语音，断网/杀进程后按原
  clientMsgId 自动重发；`VoiceOfflineQueue` 删除）；11 处空 catch 接
  runtime_exception 上报；消息发送 operation_result 遥测补齐；页面曝光/停留由
  路由级 page_open/page_return 自动埋点承载。
- 运维：`quwoquan_l2_chat_objects` 告警组（SendMessage 错误率/P95、ListInbox
  P95、ListMessages 错误率对照 metadata SLO）。
- 测试证据：chat-service api_integration 全量绿（inbox 投影链/事件 outbox/
  治理命令/群头像/fixture seed）；`aggregate_command_contract` 与
  `chat_send_outbox` 新合同测试绿。chat mock 物理迁包与 10 页专项埋点扩展
  依赖 DTO 下沉 contracts 包，登记 backlog 递延；实时 E2E 绑定 B10。

```text
执行业务对象推广批次 B5（消息）。
范围对象：messages/conversation、messages/conversation_membership、messages/message、messages/conversation_user_state、messages/message_receipt_fact、messages/chat_inbox_view、messages/conversation_search_item_view、messages/message_search_item_view。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B5 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：comment_service.go（命名迁移 + no-op receipt）、post_publication.go（一次提交：消息发送幂等参照）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；无新增决策项，但实时推送缺口必须在 acceptance 诚实标注并绑定 B10。
- 完成清除项（ChatRepository 拆分、4 处合成数据伪实现清除、chat mock 迁移、空 catch 结构化、chat 页面埋点）与断点补齐（单体 store 拆 packet、发送→outbox→inbox→已读回执闭环）。
- 逐对象走七步 DoD；message 发送使用稳定客户端 messageId 作幂等身份（一次提交模板）。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物、端侧合成成功数据。
完成后：跑 §2.6 通用门禁 + chat 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B6 实体主页（5 对象，可与 B1–B5 并行）

范围：`entity/homepage`、`entity/homepage_claim_request`、`entity/homepage_review`、`entity/homepage_status_report`、`entity/homepage_search_item_view`。

执行结果（2026-07-19）：用户侧收敛为 Homepage/Claim/StatusReport/Review 四对象，治理操作归 Ops portal；Review 采用软删复活 + CAS/receipt/outbox，评价摘要改真实聚合投影，硬编码主页 seed 退役。完整证据见 CR-120 B6 entry。

清除项：

- `HomepageRepository`（16 方法，抽象与 ~600 行 `MockHomepageRepository` 同文件）拆对象级 Facet；`homepage_mock_data.dart`（442 行）、`entity_object_page_bundle_mock.dart`（226 行）、`MockHomepageIntroductionRepository` 迁移；`app_providers_client_sync.dart` 运行时 Mock/Remote 切换删除。

补齐断点：

- homepage_review 写模型双端零实现（metadata 已声明 Create/Update/Delete，gap `HOMEPAGE_REVIEW_WIRING`）：全新建对象 packet + 端侧写评价入口 + 三层测试——B6 是唯一"从零建全新对象"的批次，严格按七步 DoD 顺序执行。

决策项（先向用户确认）：homepage 审核动作（`:review` 治理操作）归属 App 还是 Ops portal。

```text
执行业务对象推广批次 B6（实体主页）。
范围对象：entity/homepage、entity/homepage_claim_request、entity/homepage_review、entity/homepage_status_report、entity/homepage_search_item_view。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B6 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：profile_update_proposal 全 packet（domain/facade/store/transport/端侧 Facet/三层测试）——homepage_review 从零建对象以它为完整参照。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；homepage 审核动作归属（App vs Ops portal）先向用户确认。
- 完成清除项（HomepageRepository 拆分、三个 mock 文件迁移、运行时切换删除）与断点补齐（homepage_review 全新对象 packet：metadata→codegen→服务端→端侧→三层测试→readiness）。
- 逐对象走七步 DoD。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + entity 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B7 搜索与标签（9 对象，可并行）

范围：`search/query`、`search/recent_search_state`、`search/search_feedback_fact`、`search/search_recommendation_signal_fact`、`search/search_index_view`、`tag/tag`、`tag/tag_feedback`、`tag/taxonomy_release`、`tag/object_tag_index_view`。

执行结果（2026-07-19）：recent_search_state 归位 search-service 并落 Mongo CAS/receipt 有界状态，search/tag feedback typed 写面闭环，taxonomy_release 完整实现，object_tag_index 维持共享派生读模型、不造 projection 命令。完整证据见 CR-120 B7 entry。

清除项：

- `tag_mock_data.dart`（1826 行，全仓最大 fake 数据体）+ `MockTagRepository` 迁移；tag/search 域 `AppDataSourceMode` 引用清零。
- `AppSearchRepository`（1339 行，超 R03 红线）拆分。
- recent search 的裸 `Exception` 改 runtime mapper 结构化；`String.hashCode` 派生 wire `entryId` 改稳定哈希（幂等键不得依赖平台相关 hashCode）。

补齐断点：

- 搜索反馈上报：云侧 `POST /search/feedback` → Redis Stream → 推荐信号链已闭环，端侧零调用——结果页接 `ReportSearchFeedback`（impression/click/dwell/refine + `searchRequestId`/`rankPosition`/`referralSource` 归因字段）。
- recent_search_state 三方漂移收口：metadata 归 search-service（`/search/recent`）、实现在 user-service（`/user/search/recent`）、App 调 `/search/recent` 经网关必 404——先决策归属（建议按 bounded context 收编进 search-service 或 metadata 改归 user 域），再统一 path 并重生 codegen。
- search_index_view 登记 6 域 vs 实现 4 域的口径差在 metadata 注明（chat 本地检索、location 走 LocationSearchReader 属有意设计）。

决策项（先向用户确认）：tag_feedback 与 taxonomy_release 写模型——实现 or 维持显式空 routes/离线导入（`cmd/import`）。

```text
执行业务对象推广批次 B7（搜索与标签）。
范围对象：search/query、search/recent_search_state、search/search_feedback_fact、search/search_recommendation_signal_fact、search/search_index_view、tag/tag、tag/tag_feedback、tag/taxonomy_release、tag/object_tag_index_view。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B7 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：comment_service.go（recent_search_state 命名迁移参照）、outbound_share fact 链（search feedback fact 上报参照）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；两个决策先向用户确认：recent_search_state 归属（search-service vs user 域）、tag_feedback/taxonomy_release 写模型实现或显式维持现状。
- 完成清除项（tag mock 迁移、AppSearchRepository 拆分、裸 Exception 与 hashCode 幂等键修复）与断点补齐（搜索反馈端侧上报、recent_search_state 三方漂移收口、search_index_view 口径注明）。
- 逐对象走七步 DoD；fact 不加公开 operation。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + search/tag 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B8 助手（7 对象，可并行）

范围：`assistant/assistant_conversation`、`assistant/assistant_run`、`assistant/skill_subscription`、`assistant/skill_consent`、`assistant/assistant_turn_view`、`assistant/assistant_interaction_event`、`assistant/assistant_scorecard_fact`。

执行结果（2026-07-19）：Conversation/Run 从进程内 map 迁 Mongo packet，SSE 按持久终态重放；consent 版本化事实 + 双执行点 fail-closed；cron claim 改 Redis 租约；端侧聚合 Repository 拆 8 Facet 且 Remote-only。完整证据见 CR-122。

页面商用续章（2026-07-20）：找私助对话补结构化错误可见/原请求重试、欢迎空态与真实 phase；首页助手入口恢复真实 half sheet 并接通个性化、chips 与首条问题透传；技能中心删除 8 个本地假开关和演示订阅载荷，仅允许更新服务端已存在订阅；任务/记忆对象进入真实页面四态；悬空订阅 controller、开发回放面板和死 ScheduleRow 删除；assistant 页面用户文案与视觉 token 收口。证据见 CR-122 entry 2、assistant local_contract 38 例、cloud local_contract 8 例和页面 UAT 20 例。

清除项：

- `RemoteAssistantRepository` 约 10 处吞异常返回 fallback policy——改结构化 `RuntimeFailure`，禁止静默降级；production 对 mock fixture 的 import 清除。
- 1848 行三合一聚合 Repository 拆对象级 Facet；assistant 页面（5 页）零埋点补齐。

补齐断点：

- 服务端 conversation/run 内存 map 换真实 Mongo store packet（全仓最大服务端 fake；metadata storage.yaml 已声明 mongodb）。
- 学习回路端侧接入：interaction_event/scorecard 服务端就绪、端侧零调用——按 fact 上报模板接通。

```text
执行业务对象推广批次 B8（助手）。
范围对象：assistant/assistant_conversation、assistant/assistant_run、assistant/skill_subscription、assistant/skill_consent、assistant/assistant_turn_view、assistant/assistant_interaction_event、assistant/assistant_scorecard_fact。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B8 节
3. .cursor/rules/01-arch-constraints.mdc §2.5；.cursor/rules/10-runtime-error-cutover.mdc
标本参照代码：comment_aggregate_mongo_store.go（Mongo state/receipt/outbox 原子 commit 参照，用于替换内存 map）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；无新增决策项。
- 完成清除项（吞异常 fallback 结构化、production mock fixture import 清除、聚合 Repository 拆分、assistant 页面埋点）与断点补齐（conversation/run Mongo store packet、学习回路端侧 fact 上报接通）。
- 逐对象走七步 DoD。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物、异常静默降级。
完成后：跑 §2.6 通用门禁 + assistant 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B9 推荐与运营（10 对象，可并行）

范围：`recommendation/model_release`、`recommendation/recommendation_intersection_visit_state`、`recommendation/recommendation_exposure_fact`、`recommendation/recommendation_feedback_fact`、`ops/experiment`、`ops/experiment_assignment_fact`、`ops/event_record`、`ops/visit_record`、`ops/config_layer`、`ops/config_entry`。

补齐断点：

- model_release：Stage/Activate/Rollback 只有 metadata（blocked、无 Facade 实现）——若确认 V1 必需则按命名状态迁移模板补 packet（internal CAS，公开请求不带版本，本会话已从 metadata 删除 expectedVersion/idempotencyKey 字段）。
- event_record：端云链路已通，补真实 SLS/gamma 环境证据。

模型要点：`UpdateExperimentRollout` 是 If-Match 参照实现（与 B4 的 circle 样例共同构成第三类全部 3 例；`UpdateServiceConfig` 已随配置 IaC 化退场）；exposure/feedback fact 服务内闭环、不加公开 operation；config 域重建为 ConfigSnapshot 只读快照（external_reference）。

决策项（先向用户确认）：model_release 是否 V1 商用必需（不必需则 metadata 标 deferred，不实现）。

**收口记录（2026-07-19，CR-20260719-120 entry 2）**：已按用户拍板完成——model_release
生命周期三命令 deferred（`aggregate.yaml#deferred_operations`，评分 Reader 翻 ready）；
intersection_visit_state 迁 `content/` 域并重建为 per-dimension 单调水位模型（路由接通、
typed writer 拆分）；visit_record 改 aggregate_root 计数状态并落 Idempotency-Key 两阶段
台账去重；exposure/feedback fact 确定性 eventId dedupe + modelBucket/modelVersion 归因
（modelReleaseId 保持 NULLABLE 缺口注记）；guard If-Match 放行 `"0"`；experiment app consumer
deferred，AB 双轨登记 R-OBJ-004。event_record 查询 4 op 诚实保持 blocked（R-TELEMETRY-001）。
7 对象 readiness.yaml + 10 对象 tests 三件套 + `quwoquan_l2_ops_objects` 告警组落地。

**更新（2026-07-20，配置 IaC 收口）**：`ops/config_layer`+`ops/config_entry` 聚合与
`UpdateServiceConfig`/`ListConfigLayers`、pgoutbox 租约投递器、platform-ops Redis 依赖
整体退场；对象重建为 `ops/ConfigSnapshot` external_reference（只读快照 4 query：
ListServiceConfigs/ResolveEffectiveConfig/GetConfigSnapshot/ListConfigDomains）。
配置唯一真相源为版本化发布包（服务 configs 树 + 端侧 App 配置 + 数据工程 catalog），
release 配置仅保留当前灰度与上一版本（`prune_config_releases.py --check` 门禁）。
If-Match 第三类参照实现只剩 `UpdateExperimentRollout`（与 circle 两例共 3 例）。

```text
执行业务对象推广批次 B9（推荐与运营）。
范围对象：recommendation/model_release、recommendation/recommendation_intersection_visit_state、recommendation/recommendation_exposure_fact、recommendation/recommendation_feedback_fact、ops/experiment、ops/experiment_assignment_fact、ops/event_record、ops/visit_record、ops/config_layer、ops/config_entry。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B9 节
3. .cursor/rules/01-arch-constraints.mdc §2.5
标本参照代码：profile_update_proposal/facade.go（命名迁移 + 有限重试，model_release 参照）、ops 域 UpdateExperimentRollout/UpdateServiceConfig 的 If-Match 实现（第三类参照）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；model_release 是否 V1 必需先向用户确认（不必需则 metadata 标 deferred）。
- 完成断点补齐（model_release packet 或 deferred、event_record SLS/gamma 证据）；exposure/feedback fact 保持服务内闭环不加公开 op。
- 逐对象走七步 DoD。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + recommendation/ops 域定向测试；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B10 实时与通话（6 对象，依赖 B5 完成后回归其实时 E2E）

> 进度（2026-07-20，CR-20260719-121）：服务端与契约、realtime-gateway 第一方实现、RTC CAS/receipt/outbox、可信鉴权、单实时通道与 ticket 流已闭合；App 已切 5 个 generated typed Facet + production Remote-only，Mock 迁独立 alpha 包，真实来电/GetCall、成员展示组合、RTC CallEnded→chat `system_call_log`、结构化错误、语义 token、连接埋点与三条行为型 UAT 完成；RTC 全量 api_integration、gateway local_contract、metadata/codegen/Mock/包边界门均绿。Gamma package `.qwq_output/env/gamma/runs/20260719T213737Z-package-gamma-local` 成功。**唯一剩余 GATE_BLOCK**：本机缺受控 SLS secret，stackctl full workload 在 `.qwq_output/env/gamma/runs/20260719T213942Z-up-gamma` fail-closed，尚不能取得 gamma cold-start/LiveKit 运行制品或把 commercial.status 翻 ready。call_recording 已删除；presence_view 与 channel_ingress_receipt 显式 deferred。

范围：`realtime/connection`、`realtime/channel_ingress_receipt`（deferred）、`realtime/presence_view`（deferred）、`rtc/call_session`（含 `call_participant`）、~~`rtc/call_recording`~~（已删除）。

清除项：

- `lib/cloud/services/rtc/mock/rtc_mock_data.dart` 整目录迁 `quwoquan_cloud_mock`；`RtcRepository`（17 方法三合一）拆对象级 Facet 并改 generated client + Remote-only 装配；rtc 5 页零埋点补齐 + 通话质量事件进 telemetry catalog（metadata-first）。

补齐断点（本批最重）：

- realtime-gateway 当前为幽灵服务（仅 `configs/`+`deploy/kustomize/`，无源码）：先决策"独立实现 or 归并进既有进程"（改 `process_domain_mapping.yaml` 拓扑），再落 Connection（redis lease+fencing）/PresenceView packet。
- 信令统一：App 连 `/realtime/ws`、rtc 服务端实际在 `/rtc/signal`，且 auth 协议不匹配（服务端回 `auth_ok`、App 等 `auth_ack`）——metadata 冻结唯一端点与协议，两端同改。
- `adapters/ws/signal_handler.go` JWT 鉴权占位（query userId 直取、auth 直接放行）补真实校验。
- chat 实时推送 E2E 回归（B5 遗留项）。

决策项（先向用户确认）：

- call_recording 录制链三重断（orchestrator 从不调 LiveKit Egress、recordingId wire 双端错位、无独立 store）——V1 接通 or 显式砍（推荐砍：metadata 标 deferred + 删死代码）。
- channel webhook（channel_ingress_receipt）落地范围。

```text
执行业务对象推广批次 B10（实时与通话）。
范围对象：realtime/connection、realtime/channel_ingress_receipt、realtime/presence_view、rtc/call_session（含 call_participant）、rtc/call_recording。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节（重点 runtime_session：lease+fencing、RUNTIME-SESSION-010）
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B10 节
3. .cursor/rules/01-arch-constraints.mdc §2.5；quwoquan_ops/environments/process_domain_mapping.yaml
标本参照代码：notification/location 端侧轨道（RtcRepository 拆分目标形态）、comment_aggregate_mongo_store.go（store 范式）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；三个决策先向用户确认：realtime-gateway 独立实现 or 归并进程、call_recording V1 接通 or 砍（推荐砍）、channel webhook 落地范围。
- 完成清除项（rtc mock 迁移、RtcRepository 拆分、rtc 页面埋点+通话质量事件）与断点补齐（realtime session packet、信令端点与 auth 协议统一、signal_handler JWT、chat 实时 E2E 回归）。
- runtime_session 严格按 lease+fencing 模板；webhook 先归一 receipt fact 再事件投递。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物、把 webhook 声明成 session command。
完成后：跑 §2.6 通用门禁 + realtime/rtc 域定向测试 + chat 实时 E2E；更新 readiness/acceptance/CR/backlog（含拓扑变更）；输出 Exit Review 七项。
```

### B11 集成与通知（6 对象，收尾批）

范围：`integration/external_interaction`（含 attempt/dead_letter fact）、`integration/location`、`notification/notification`、`notification/notification_delivery_job`。

执行结果（2026-07-19）：七源互动事件经 durable stream → notification-service → AppMessage inbox 闭环，消息页通知维度支持真实渲染/路由/已读/徽标；push 外送按用户决策显式 deferred 为站内信，不保留假 provider。完整证据见 CR-120 B11 entry。

清除项：

- notification delivery adapter 硬编码 path `/integrations/external-requests` + 4 个 `INTEGRATION.*` 错误码字符串改 generated 常量。
- 全仓收尾：`AppDataSourceMode` 本体删除（`lib/core/di/app_data_source_mode.dart`）+ 棘轮基线归零（前置：B1–B10 各域引用已清零）。

补齐断点：

- 业务事件 → notification 生产者：当前仅 assistant 接入，chat/content/circle 业务事件不产生通知——按域接 notification 生产（评论/点赞/关注/圈子申请等通知场景，metadata-first 声明事件消费）。
- 通知中心/未读入口页面（当前无 `lib/ui/notification/`）：新页面 + 页面矩阵登记 + 埋点；AppMessage 未读数接消息 tab。

决策项（先向用户确认）：push provider（APNs/FCM）+ App token 注册——V1 实现 or 显式降级站内信（metadata 标注）。

```text
执行业务对象推广批次 B11（集成与通知，收尾批）。
范围对象：integration/external_interaction（含 attempt/dead_letter fact）、integration/location、notification/notification、notification/notification_delivery_job。
必读（按序）：
1. specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md「按真实写入场景裁剪并发与幂等」一节
2. specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/object-batch-rollout-plan.md §1–§2 与 §5 B11 节
3. .cursor/rules/01-arch-constraints.mdc §2.5；.cursor/rules/09-page-horizontal-quality.mdc（新增通知中心页面须更新页面矩阵）
标本参照代码：notification 域已是端侧新轨道（app_message_facets_remote.dart）；reliabletask 平台（attempt/dead_letter fact 已实现）。
执行要求：
- 先输出 Spec Entry 与 Pre-work Reflection；push provider 实现 or 降级站内信先向用户确认。
- 完成清除项（delivery adapter path/错误码 generated 化、AppDataSourceMode 本体删除与棘轮归零——若 B1–B10 尚有域未清零则只收敛本域并诚实说明）与断点补齐（业务事件→notification 生产者、通知中心页面+页面矩阵+埋点+未读接入）。
- 逐对象走七步 DoD。
- 禁止：新增 If-Match、通用 Saga、聚合 Repository、lib 内 mock、手改 codegen 产物。
完成后：跑 §2.6 通用门禁 + integration/notification 域定向测试 + make verify-app-page-horizontal-quality；更新 readiness/acceptance/CR/backlog；输出 Exit Review 七项。
```

### B12 横向商用成熟度收口（跨批复盘）

范围：不新增业务对象；横向修复 B2–B11 暴露的 fake、契约单轨、Mock 隔离、
页面三态与矩阵证据失真。

执行结果（2026-07-19）：

- search 灵感页只消费真实 hot query/circle/location 数据，云端空结果保持空态；
  assistant 管理页删除无真实 operation 支撑的清除记忆按钮与静态假进度。
- `feed_object_card` 删除 schema version/aliases；circle 只读 canonical `id`；
  chat/circle/notification 事件身份改业务键，single-track findings 清零。
- UserRepository Mock 物理拆到 mock 子目录，user/user-profile 生产组合根改
  Remote-only，alpha 显式 override；profile media PUT 统一走 CloudHttpClient。
- chat 会话页拆为 519/862 行并补 loading/空态/错误重试；群管理/成员搜索/
  聊天信息页消费 provider 错误；RTC 通话页补建连加载与可重试错误面；
  profile 首屏错误改 `RuntimeFailureBase`；主页认领文案 token 化。
- 页面矩阵统计重算为 81 行，P6 partial 清零；本节及 B4/B6/B7/B8/B11
  执行结果回写，消除 CR 与计划文档漂移。

## 6. 关联产物

| 产物 | 说明 |
|---|---|
| 本文件 | 12 批次唯一执行顺序、范围与出口定义 |
| [design.md](../design.md) | 七类对象并发/幂等规则、三分类写入、no-op receipt、跨聚合检查点真相源 |
| [acceptance.yaml](./acceptance.yaml) | 本 story 验收与 `execution.local_gate` 门禁 |
| `specs/changelog/CR-20260719-120-business-object-batch-rollout.yaml` | 本计划变更登记 |
| `docs/outstanding_risks_backlog.md` | 勘察确认的长期风险（对象级告警断链、多域零埋点、realtime-gateway、通知推送链） |

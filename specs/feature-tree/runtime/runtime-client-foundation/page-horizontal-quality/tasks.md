# page-horizontal-quality 任务

## 当前交付

### M1：索引与门禁可追溯

- [x] `spec.md` / `design.md` / `acceptance.yaml` / `plan.yaml` 与本目录并列
- [x] 指向父目录 `page-horizontal-quality-spec.md`、`page-horizontal-quality-matrix.md` 与 `scripts/verify_page_horizontal_quality_matrix.py`

### M2：/baseline 冻结（2026-03-29）

- [x] `page-horizontal-quality-spec.md` 增补商用/NFR（治理型）
- [x] `design.md` 上游评审、方案对比、观测与回滚
- [x] `acceptance.yaml` T3/T4 证据矩阵 + A3（CR-005）
- [x] `plan.yaml` slice-2
- [x] `CR-20260329-005-page-horizontal-quality-baseline.yaml`

### M3：/dev 无漏页门禁（2026-03-29）

- [x] `scripts/verify_page_matrix_scan_complete.py`（磁盘 = 矩阵 ⊆ 缺口清单）
- [x] `scripts/gate_repo.sh` 串联调用
- [x] 矩阵挂靠面补 `_AssistantConversationHistoryPage`

### M4：九会话横向落实规划（2026-03-29）

- [x] `nine-session-rollout-plan.md`（S1–S8 一维一会话，S9 收口；**P7/P8 会话分离**）
- [x] `CR-20260329-006-page-horizontal-quality-nine-session-rollout.yaml`
- [x] `plan.yaml` slice-3、`acceptance.yaml` A4、`spec.md` 索引

### M5：S2（P2）登记基线冻结（2026-03-30）

- [x] `CR-20260330-007-page-horizontal-quality-s2-p2-baseline.yaml`
- [x] `plan.yaml` slice-4、`acceptance.yaml` A5、`design.md` §S2、`spec.md` CR 索引
- [x] `s2-metadata-driven-contract-baseline-20260330.md`（全页对照 + 基线锁定声明）

**执行跟踪（由各独立会话勾选）**

- [x] **S1** P1 iOS 原生 — 矩阵 P1 列收口（门禁已含 `app/shell`，与矩阵扫描基线对齐；`verify_*` + `gate_repo.sh --scope app` 通过）
- [x] **S2** P2 元数据 — 矩阵 P2 与 `metadata_driven_ui_gap_inventory.yaml` 已逐格对齐（64 行 0 漂移）；全页分析与基线锁定见 [`s2-metadata-driven-contract-baseline-20260330.md`](./s2-metadata-driven-contract-baseline-20260330.md)
- [x] **S3** P3 端云 — 页级无 `package:http`；矩阵 P3 维持 ✓/—（2026-03-30 审计）
- [x] **S4** P4 埋点 — `GoRouter` + `AppPageAccessNavigatorObserver`、`page_access_log_util`、Welcome `/welcome`；矩阵 P4 全 ✓
- [x] **S5** P5 组件复用 — 矩阵与门禁 `verify_settings_canonical` / `verify_conversation_sheet_canonical` 同向登记
- [x] **S6** P6 双色 — 矩阵与 `page-dual-theme-matrix.md` 交叉更新（partial 行保留 ○）
- [x] **S7** P7 断点/版式 — 矩阵 P7 ○→✓（取景区 `camera_capture` 仍 —）
- [x] **S8** P8 语义 token — `verify_dart_semantic` 通过；矩阵 P8 维持 ✓
- [x] **S9** 收口 — 剩余 **P2** 登记技术债 **PHQ-P2-TBD**；`gate_repo.sh --scope app` OK；`CR-20260330-008`

### M6：P2 全量收敛 — 切片 1（2026-03-30）

- [x] `metadata-driven-client-data-contract/design.md` §7（TBD→目标 DTO + DDD 边界）
- [x] `ChatMessageDto` codegen + `listMessages` 强类型；`CR-20260330-009`
- [x] 清单 **target_dto: TBD 清零**（仍 `partial` 的页保留滚动收口）
- [x] 矩阵 `chat_detail` / `chat_conversation` **P2 ✓** 与统计区更新
- [x] **`start_group_chat_page`**：`circleId` inbox 投影、`ChatConversationCreatedDto`、`createConversation` 强类型；清单 chat 域全 **compliant**；矩阵 **P2 ✓** 与统计 10/42

### M7：Phase7–9 rtc + assistant 收口 + 矩阵/清单（2026-03-30）

- [x] rtc：`CallPickerParticipantRow`、`ChatInboxDto` 群横滑；`CallParticipantPickerRouteExtra`；`voice`/`video`/`chat_conversation`/`app_router` 全量 typed extra
- [x] assistant：`AssistantLocalSessionSummaryView` / `AssistantSessionDetailView` / `AssistantPreferenceFactView`；`assistant_skill_center_page`、`assistant_chat_settings_page` 去页内会话/偏好 Map
- [x] `metadata_driven_ui_gap_inventory.yaml` rtc 全 **compliant**；assistant 对话页仍 **partial**，其余非 exempt **compliant**
- [x] `page-horizontal-quality-matrix.md` rtc 与 assistant 四页 **P2 ✓**；统计 **51 / 1**；`verify_page_matrix_scan_complete` + `verify_metadata_driven_ui_gate` 绿

### M9：S8（P8）语义 token 子 L3 /baseline（2026-03-30）

- [x] `../s8-p8-semantic-token/`：`spec.md` / `design.md` / `plan.yaml` / `acceptance.yaml`
- [x] `CR-20260330-012-s8-p8-semantic-token-baseline.yaml`；`tree_index` 注册 **s8-p8-semantic-token**（tag **S8**）
- [x] 父 L3：`plan.yaml` slice-7、`acceptance.yaml` **A9**、`spec.md` 索引、`page-horizontal-quality-spec.md` 交叉引用
- [x] **W0–W5 代码波次**：`verify_dart_semantic` 全量绿；`.verify_dart_semantic_baseline.txt` 仅注释头（2026-03-30 收口）

### M8：实施波次 B — Mock · 端云 · 测试编译隔离（**§5.1 规格基线已冻结**；部分工程项仍可选）

> **规划**：[`nine-session-rollout-plan.md`](./nine-session-rollout-plan.md) **§实施波次 B**；策略 [`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md) **§4.1、§9、§5.1**；PR 清单 Mock 节。  
> **登记**：[`CR-20260330-010-mock-isolation-implementation-wave.md`](../../../../changelog/CR-20260330-010-mock-isolation-implementation-wave.md)；**§5.1 流程/验收基线** [`CR-20260330-011-mock-release-functional-spec-baseline.yaml`](../../../../changelog/CR-20260330-011-mock-release-functional-spec-baseline.yaml)。

**B0 脚手架**

- [x] `quwoquan_app/test/support/{fakes,fixtures,harness}/` + README（§9.2）
- [x] `quwoquan_app/lib/core/data_source/README.md` 占位（渐进迁出 `AppDataSourceMode`）
- [x] Chat：`chat_repository_api.dart`、`remote/chat_repository_remote.dart`、`mock/chat_repository_mock.dart` + barrel `chat_repository.dart`

**B1 清债（allowlist → 空）**

- [x] 逐条删除 [`ui_mock_isolation_allowlist.yaml`](../../../../gates/ui_mock_isolation_allowlist.yaml) 对应实现（禁止新增行）；当前 **allowed: []**
- [x] `chat_contacts_row` / `chat_contacts_rows_provider` / `chat_inbox_provider` → 仅 Repository
- [x] 圈子页 + `search_*` + `global_surface_actions` → 无 `CircleMockData` 直连 UI（门禁绿）
- [x] `app_content_repository` / `RemoteAppContentRepository` → 真 Remote 或空态（无整表委托 Mock）
- [x] `app_providers` `ChatMockData` 解耦 → 身份单源策略已对齐 §5.1

**B2 测试与编译隔离（P0b）**

- [x] `scripts/verify_lib_no_test_only_symbols.py` + [`lib_test_only_symbols_allowlist.yaml`](../../../../gates/lib_test_only_symbols_allowlist.yaml) + `gate_repo.sh --scope app`
- [ ] 将 `AssistantRuntime.createForTest` 等迁出 `lib/`（当前 allowlist 登记；清债时删行）

**B4 正式发行（运行时门控 + CI；P4 物理拆链另列）**

- [x] `main_prod` 经 [`app_bootstrap.dart`](../../../../../quwoquan_app/lib/app_bootstrap.dart) + **锁定 Remote** 的 `appDataSourceModeProvider` 覆盖；**不** import `main.dart`
- [x] CI 正式构建 `--dart-define=APP_DATA_SOURCE=remote`（`.github/workflows/app_pipeline.yml`）
- [ ] **P4 物理**：`app_providers` / `quwoquan_core` 拆 prod 专用 import 图（清单见 [`prod_bootstrap_repository_inventory.md`](../../../../gates/prod_bootstrap_repository_inventory.md)）

**波次 B 出口验证**

- [x] `verify_ui_mock_isolation.py` OK 且 allowlist **空**
- [x] `verify_page_matrix_scan_complete.py` + `gate_repo.sh --scope app` OK（与矩阵 PR 同向）
- [x] 矩阵相关页 **P3** 与 Mock 隔离策略一致；**acceptance A8** + **plan slice-6** 登记 §5.1 基线

### M10：S9 治理收口 — 规则 / 命令 / 流程 / 门禁（登记）

- [x] `.cursor/rules/09-page-horizontal-quality.mdc`（`alwaysApply`）：触发路径、矩阵、P2 清单、命令、gate 串联
- [x] `01-arch-constraints.mdc` §2.4「横向质量矩阵」行 + `Makefile` **`verify-app-page-horizontal-quality`**
- [x] `page_horizontal_quality_pr_checklist.md` §**S9 / 持续治理** 表（规则 · 架构 · 命令 · 门禁 · 流程）
- [x] `nine-session-rollout-plan.md` / `page-horizontal-quality-spec.md` / `spec.md` 索引交叉引用
- [x] `CR-20260330-014-page-horizontal-quality-s9-governance-closure.yaml`

## 后续

- [ ] 矩阵或脚本变更时同步更新本目录 `spec.md` 索引表
- [ ] 新增横向维度（P9…）时同步更新脚本 `PILLAR_COUNT` 与矩阵表头，并追加 **S10** 会话定义
- [ ] **PHQ-P2-TBD**：剩余 `assistant_conversation_page`（引擎消息 Map）等直至 P2 全 ✓

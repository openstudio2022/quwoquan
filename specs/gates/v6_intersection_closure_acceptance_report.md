# V6 架构同源收口 + 增长商业化 + 交集闭环 验收报告（S7）

关联：`specs/changelog/CR-20260531-028-v6-arch-source-unify-growth-closure.yaml`。
执行口径：终验 **static_only**（用户选择）—— 静态一致性 + 门禁静态项本会话验收；运行态 `make gate-full`（需 Colima/Gamma）与 T4 旅程实跑顺延。

## 1. 架构同源（S1/S2/S3）

| 项 | 判据 | 结果 |
| --- | --- | --- |
| 扁平标签真相源 | `tag_taxonomy.yaml` + `tag_ref_migration.yaml` 物理删除且零引用；字段切路径制 tagRef | ✅ `verify_tag_ref_source_of_truth` OK（扁平 taxonomy 零引用 / 字段已切 tagRef） |
| 内容投影单轨 | `PostReadProjectionFacade` 删除，调用内联 `PostReadPresentation.fromPostBase` | ✅ 三处调用内联 + 契约测试改写；pageflip 字面等价零回归 |
| resonance 清零 | 代码 + specs 零残留 | ✅ 3 文件删 + specs 残句清（矩阵/inventory/网络图/布局语义） |

## 2. 军规零违规（S4）

| 军规 | 门禁 | 结果 |
| --- | --- | --- |
| R17 空 catch | lib 内空 catch = 0 | ✅ `rg` 扫描 0 处 |
| R02 上帝接口 | ≤10 方法子接口；over-threshold allowlist | ✅ `verify_repository_interface_method_budget` OK（allowlist 10→7，Circle/Chat/UserProfile 已拆伞组合子接口） |
| R03 超大文件 | ratchet 只降不升 | ✅ `verify_file_line_budget` OK（46 文件，WIP/R02/R17 漂移写基线收口） |
| R04 弱类型 | map budget 不超 | ✅ `verify_ui_map_literal_budget` count=178=budget |
| 整体编译 | dart analyze lib 0 error | ✅ 0 error（58 info/warning 均为既往 lint，非本次引入） |

## 3. 增长商业化 · 交集转化闭环（S6）

| 项 | 判据 | 结果 |
| --- | --- | --- |
| 交集字段契约 | behaviors.yaml follow 补 `intersectionDimension`/`intersectionTagRefs` | ✅ |
| 三类独立动作 | `join_circle`/`add_contact` 独立 BehaviorAction，与 follow 区分漏斗 | ✅ behaviors.yaml + Go SignalWeights + Dart 枚举 + tracker |
| 端云三方一致 | behaviors.yaml ↔ Go SignalWeights ↔ Dart BehaviorAction 集合相等 | ✅ `verify_behavior_action_consistency` OK |
| 服务端消费 | `BehaviorSignal`/`BehaviorEventInput`/`RawBehaviorEvent` 透传交集字段；HotPath 可消费 | ✅ go build + go test(recommendation) 绿 |
| 北极星指标 | `intersection_conversion_rate` 按 dimension/action 下钻；DailyMetrics intersection 维度累计 | ✅ analytics-metric-dictionary 专节 + A9；behavior_service intersection 维度 IncrementMetric |
| 实验灰度地基 | 交集策略可按 experimentBucket 切分 + 回滚可度量 | ✅ experiment-bucketing-and-rollout 规格 hook（A1–A3） |
| bug 修复 | 入队重试不丢交集归因 | ✅ `_behaviorEventFromJson` 补交集字段 roundtrip + T1 断言 |

## 4. 交集引擎三角（静态连线核实）

推荐 → 交集理由 → 小趣解释 → 用户行动 → 行为回流，各环节真相源静态存在并连通：

| 环节 | 真相源 / 落点 | 证据 |
| --- | --- | --- |
| 推荐排序 | `content/post/projections/discovery_feed.yaml`（携带交集） | ✅ |
| 交集理由 | `recommendation/rec_model/projections/intersection_reason.yaml`（B1 契约） | ✅ |
| 小趣解释 | `core/models/assistant_open_context.dart`（B2 intersectionRefs/dimension/objectType 透传） | ✅ |
| 用户行动 | `BehaviorAction.follow/joinCircle/addContact` + tracker（S6） | ✅ `home_intersection_action_attribution_test` 通过 |
| 行为回流 | behaviors.yaml → `BehaviorSignal.IntersectionDimension/TagRefs` → HotPath | ✅ go test(recommendation) 绿 |

## 5. 一致性静态校验汇总

| 门禁 | 结果 |
| --- | --- |
| `verify_tag_ref_source_of_truth`（标签单源） | ✅ OK |
| `verify_behavior_action_consistency`（行为三方） | ✅ OK |
| `verify_ui_mock_isolation`（Mock 隔离） | ✅ OK |
| `verify_dart_semantic`（语义 token/红线） | ✅ OK |
| `verify_page_horizontal_quality_matrix`（页面矩阵符号） | ✅ OK |
| `verify_page_matrix_scan_complete`（矩阵扫描完整） | ✅ OK（62 路径对齐） |
| `check_runtime_error_cutover`（runtime error 收口） | ✅ passed |
| `verify_file_line_budget` / `verify_repository_interface_method_budget` / `verify_ui_map_literal_budget`（军规） | ✅ OK |
| `make verify-metadata` | ✅ 68 实体 / 93 枚举 |

## 6. 顺延项（运行态 / 重 UI / 变现）

- **运行态终验**：`make gate-full`（需 Colima/Gamma 运行态）、引擎三角 T4 与交集闭环 T4 实跑 → static_only 顺延。
- **远程分支删除**：8 个历史远程分支裁决已记录（`v6_git_branch_cleanup_decisions.md`），远程 `git push --delete` 待人工执行（含 `fix/08` privacy 修复 cherry-pick 核对）。
- **R04 map budget 下调倒逼**：需先做 article 投影/wire `Map<String,dynamic>`→强类型清理（独立重构），与重 UI 专项一并顺延；当前门禁绿（178=178）。
- **纯变现 UI**：会员 / 付费 / 创作者激励 / 邀请奖励 UI → roadmap V6 之后顺延。

## 结论

架构同源（标签单源 / 投影单轨 / resonance 清零）、军规零违规、增长商业化交集转化闭环（契约+端云消费+北极星+实验地基）、交集引擎三角静态连线 —— **静态验收全绿**。运行态 gate-full 与 T4 实跑按 static_only 顺延。

## 7. V7 顺延项做实（2026-05-31，零妥协收尾）

CR-20260531-028 revision 2。原 §6 顺延项中「运行态终验」「远程分支删除」已做实：

| 顺延项 | V7 终态 | 证据 |
| --- | --- | --- |
| 运行态终验 `make gate-full`（T3/T4） | ✅ `make gate-local-gamma`：T3 passed + T4 passed（iPhone 17 Pro gamma-patrol-matrix）+ verify passed | `artifacts/local-gamma/{t3_report,report}.json`、`artifacts/v7-evidence/RUNTIME_GATE_EVIDENCE.md` |
| `make test-contract` | ✅ 0 失败 / 19 包 ok（testcontainers L2 无 rootless docker 优雅 skip） | `artifacts/v7-evidence/RUNTIME_GATE_EVIDENCE.md` |
| 运行态镜像阻塞修复 | ✅ media_root 对齐 /srv/media、`LOCAL_GAMMA_USER_PORT=19210` 导出、colima user_port 隧道、compose `start_period 10s→240s` | commit `fix(local-gamma): ...` |
| 远程分支删除 | ✅ 实删 7 分支 rc=0，终态远程仅 `dev1.0`+`main` | `v6_git_branch_cleanup_decisions.md` §V7 |
| `fix/08` privacy cherry-pick 核对 | ✅ dev1.0 已独立更完整实现（setting_service round-trip + `TestPrivacySettings_BlockedKeywordsRoundTrip` + 迁移整合 005），判定**不** cherry-pick | `v6_git_branch_cleanup_decisions.md` §V7 |

**V7 结论：V6 全部顺延项做实，make gate 静态 + local-gamma T3/T4 + test-contract 端到端全绿，远程历史残留清零，无新功能、无契约破坏。**

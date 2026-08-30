# L2 Design：统一控制面基础 (`runtime-control-plane-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口”需要 `domain-onboarding-acceptance-governance` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`domain-onboarding-acceptance-governance`](./domain-onboarding-acceptance-governance/spec.md)：不存在第二真相源，且统一门禁能够发现路径、拓扑、配置和证据漂移。
- [`human-authority-role-cards`](./human-authority-role-cards/spec.md)：Portal 投影四类卡并接收限权 submission，决定、授权与 effect 继续由 Human-Agent / hosted authority 边界拥有。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 控制面状态归所属服务写入并由统一门户组合查询
- 决策：控制面状态归所属服务写入并由统一门户组合查询。
- 理由：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`domain-onboarding-acceptance-governance`](./domain-onboarding-acceptance-governance/spec.md)
- 关联验收：`SIT-001`


<a id="dec-002"></a>
### DEC-002 Portal 只消费 provider-owned RoleTask/CardProjection，所有 mutation 由限权 capability 单轨执行
- 对象与 Query owner：Hosted Human Authority provider 是 authenticated `RoleTask/CardProjection` query 的唯一 owner。投影必须绑定 `DecisionUnit/candidate/scope`、verifier 映射后的 actor principal、恰好一个 pending role/task capability、canonical 四类卡、round/stage/state、allowed operations、安全默认、pending roles、到期/证据/认证 freshness、recommendation visibility、recovery state 与脱敏 role projection。raw aggregate、audit、evidence bytes 与 chain proof 只由分离的 least-privilege audit query/scope 返回，永不作为角色卡 fallback。
- Portal 边界：`quwoquan_ops/portal` 只严格解析 generated projection 与 generated operation capabilities；未知 schema/version/card/state/operation、缺字段、额外语义或旧 unversioned projection 一律 `projection_schema_mismatch` fail-closed，关闭 mutation 并保留安全重新认证/重新查询入口。禁止由 aggregate 推导 current role/status/actions、禁止 `intake` 影子卡、禁止 client fallback/default、禁止把菜单权限或按钮可见性当服务器授权。
- 命令边界：Portal 对 role submission、request-evidence、transfer、pause/hold/abort 与独立 post-check/result-acceptance 分别调用一个 capability/command；每条 command 单独返回 committed/duplicate/conflict/blocked/outcome_unknown 及 authority readback ref。Portal 不组合 submit+seal，不把 submission 成功提升为 round sealed/finalized，也不在 post-check 再 finalize。unknown outcome 先按 operation/idempotency key query committed response，再允许相同 request digest 的安全 replay。
- 多角色与 seal：role task capability 允许同一 authenticated principal 在 `role-record-only` 下按不同角色逐条提交，且成功投影明确返回 accepted/pending/next-role。`independent-principal-required` 继续验证不同 actor。
- seal 所有权：最后一份合法 submission 由 provider 在同一 PostgreSQL 事务自动 seal 对应 round，不设置独立通用 seal writer。需要人工或编排恢复时只能使用 provider-issued `seal-orchestrate` capability，generic write scope、creator、普通 role 与 Portal 本身均无 seal 权限。
- Recommendation：Portal 只展示 provider 投影的 recommendation。provider 只有在 required rounds 已封存后才能投影，且必须同时给出 assumptions、counterexamples、alternatives；产品范围、体验方向、商用与 outcome 等 canonical 禁止类始终不可见。Portal 不以本地 sealed-round 推导、手写 gate 或自行排序补推荐。
- 身份与错误 UX：Portal 使用 Authorization Code + PKCE、一次性 state/nonce，并在 provider 返回 auth freshness 过期时触发 re-auth。401 只表示未认证/credential 无效或过期，403 分别承载 scope denied 与 wrong role；stale task、hard veto、projection mismatch、outcome unknown 等保持各自 typed terminal，不折叠成通用失败或 absent。
- 无障碍结果：角色卡必须通过真实 DOM 暴露稳定的名称、角色与状态，提供可预测的焦点进入和错误回焦，支持键盘完成每个 generated operation，并由 live region 播报异步 readback；窄屏不得丢失字段或因换序改变语义。真实 screen-reader、正式 MFA principal 与跨角色可理解性继续由 external UAT `OPEN` 承担，不以机器检查冒充。
- 一致性与失败恢复：Portal 不持有 authority mutation 状态，只缓存可丢弃的 query/readback。刷新、掉线、partial response 或 outcome unknown 都重新 query provider。stale task 只能刷新 capability，wrong-role/scope 只能转交或修复 mapping，auth freshness 只能 re-auth。
- 回滚：单轨 cutover 后旧 Portal/旧 projection 不得 dual-read/dual-write。deployment rollback 可回到仍兼容新 projection 的版本；否则保持 mutation disabled，绝不恢复旧 mutation schema 或 raw aggregate fallback。
- SLI/SLO 与告警：按 `operation_capability/card_type/stage/terminal` 观测 query success、projection mismatch、stale task、wrong role、scope denied、auth freshness、re-auth、recovery command、outcome_unknown 与 reconciliation age，且禁止 actor/PII 维度。provider query p95 目标 `<=1s`，Portal 在 `100%` 未确认 mutation 上不得显示成功。schema mismatch、未授权 operation、post-check 再 finalize 或 fallback 命中预算为 0，一例即阻断该 surface mutation。
- 测试 seam：`local_contract` 锁定 generated decoder 对 unknown/missing/extra/version/card 的闭集拒绝与零 fallback。component/browser 行为证据覆盖四类卡、单 capability 一请求、每个恢复动作、submit 与 seal 独立 readback、outcome_unknown reconciliation、typed 401/403 和行为级 a11y。`api_integration` 绑定真实 provider projection/capability 与 stale/readback。`user_acceptance` 只由真实 screen-reader 与不同 MFA principals 关闭。
- 理由：角色卡是 provider authority 的限权投影，不是 Portal 对 raw aggregate 的解释。单 task capability、单 command 与 readback reconciliation 让网络未知、角色切换和多实例 provider 在不扩大权限的前提下恢复，并让 UI 无法伪造 seal/finalize。
- 被否决方案：否决 Portal 解析 raw aggregate、默认 `intake`、本地推导 current role/status/action/recommendation、submit 后顺手 seal、通用 write scope seal、post-check 复用 finalize、401/403 合并、source-regex a11y 准出、旧 wire fallback 与长期双读写。也否决把 role-record-only 错误提升为 distinct-principal。
- 适用工程根：`quwoquan_ops/portal`；Portal IA authoring metadata 为 `quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`，provider wire/capability authoring 位于 `quwoquan_service/control-plane/platform-ops/contracts/platform_ops/human_authority`，generated projection 均只读消费。
- 关联要求：`human-authority-role-cards/REQ-001` 至 `REQ-005`
- 影响 Story：[`human-authority-role-cards`](./human-authority-role-cards/spec.md)
- 关联验收：`GWT-001`、`GWT-002`、`GWT-003`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 全局通知：审批、告警、case SLA、灰度中断、回滚结果。
- 全局审计：所有危险动作、配置变更、处置动作可统一检索。
- 全局对象跳转：服务、内容、用户、圈子、实验、case、配置项可跨模块跳转。
- 高危动作趋势、双签通过率、case 周期、配置变更热区、回滚频次。

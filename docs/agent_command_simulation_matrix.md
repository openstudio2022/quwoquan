# Agent Command Simulation Matrix

本文把用户自然语言、Cursor 命令、Codex AGENTS 工作流和出口证据对齐。无论用户输入 slash command，还是直接 vibe coding，Agent 都按同一矩阵执行。

## Command Matrix

| Command | 用户自然语言样例 | Cursor 执行视角 | Codex 执行视角 | 必读上下文 | 禁止事项 | 出口证据 | 最小验证命令 |
|---|---|---|---|---|---|---|---|
| `/explore` | “先看看这个需求归属哪里” | 只读探索 workspace，定位树归属、风险和触发规则 | 按 AGENTS + command 语义输出归属，不写实现 | `AGENTS.md`、`docs/agent_context_contract.md`、`.cursor/commands/explore.md` | 写代码、改文档、跳过 L1/L2/L3 | Journey/Scenario、L1/L2/L3、UAT/SIT/GWT/contract、三层测试证据、风险 | `make verify-agent-context-contract` |
| `/prd` | “把这个需求规格冻结” | 更新或建议更新对应 spec/acceptance | 检查规格、验收、CR 和 registry 是否需刷新 | `.cursor/commands/prd.md`、特性树 spec/acceptance | 未明确 Out of Scope、缺 SLO/权限/生命周期 | `spec.md`、`acceptance.yaml`、registry/CR 更新说明 | `bash quwoquan_ops/gate/scaffold/verify_acceptance_standard.sh` |
| `/design` | “给出架构设计并冻结方案” | 在 AppRoot/L1/L2 层设计，不给 Story 新增 design | 对齐 metadata、回滚、观测、三层测试 | `.cursor/commands/design.md`、相关 `design.md` | Story 层建 design、绕过 metadata、缺回滚 | 设计边界、依赖、数据流、观测、回滚、测试矩阵 | `bash quwoquan_ops/gate/scaffold/verify_specs_l1_hierarchy.sh` |
| `/baseline` | “需求稳定，做基线” | 一次冻结 spec、acceptance、必要 design 和 CR | 检查方案是否收敛，再进入基线 | `.cursor/commands/baseline.md`、`specs/00_MASTER_DEVELOPMENT_FLOW.md` | 未收敛就冻结、用基线掩盖分歧 | spec/acceptance/design/CR/registry 对齐 | `bash quwoquan_ops/gate/scaffold/verify_feature_tree_refactor.sh` |
| `/extend` | “新增错误码 / 字段 / endpoint” | 先改 metadata，再 verify/codegen，再列手写清单 | 按扩展场景 S01-S26 执行，不手改 generated | `.cursor/commands/extend.md`、metadata README | 硬编码 path/error/codegen、跳过 verify | metadata diff、codegen 产物、手写补充清单、测试路径 | `make verify-metadata` |
| `/dev` | “实现一下 / 修这个问题” | 先做 Spec Entry + Pre-work Reflection，再 Red/Green/Refactor | 从 AGENTS 层级和命令语义派生 todo 与验证 | `.cursor/commands/dev.md`、相关区域 AGENTS/rules | 规格不清直接改、只做局部端、无证据停止 | 实现说明、测试证据、触发 gate、Exit Review | 触达范围专项测试 + `make verify-agent-context-contract` |
| `/verify` | “收口检查 / 验一下是否完成” | 对照 acceptance、三层测试、门禁和 E2E 证据 | 输出通过/缺口/需重跑命令/剩余风险 | `.cursor/commands/verify.md`、acceptance、gate 输出 | 用新计划掩盖未完成、只看 diff | 规格达成、三层测试、E2E、UX、观测、门禁、风险 | `make verify-agent-context-contract` |
| `/plan-review` | “开发前再审一遍计划” | 多角色检视规划，不写实现 | 刷新目标、规格、任务清单和验收标准 | `.cursor/commands/plan-review.md`、`13-coding-discipline.mdc` | 空泛建议、无任务落点、跳过阻断项 | 角色检查结果、不符合项台账、刷新后任务清单 | `bash quwoquan_ops/gate/scaffold/verify_acceptance_standard.sh` |
| `/plan-next` | “完成后规划下一轮” | 先验收本轮，再生成下一轮 | 不用下一轮掩盖本轮未完成 | `.cursor/commands/plan-next.md`、原 acceptance/gate | 未达成无证据却开新规划 | 完成度自检、证据核对、下一轮规格/任务/验收 | `/verify` 对账结果 |
| `/continue-dev` | “规划好了开始开发 / 这轮做完复盘后继续开发” | 规划就绪进入开发与验证；一轮完成后复盘、盘点遗留与风险、生成新一轮规划再开发 | 以最资深工程师标准裁决争议、零技术债、分层测试自顶向下闭环 | `.cursor/commands/continue-dev.md`、`dev.md`、`plan-next.md`、`docs/outstanding_risks_backlog.md` | v1/v2 并存、技术债不清、用新规划掩盖未完成、部分端/无证据停止 | 实现+Exit Review、三层测试证据、复盘与遗留/风险台账、下一轮规格/任务/验收 | 触达范围专项测试 + `make verify-agent-context-contract` |
| `/deploy` | “部署 / 发布 / 放量 / 回滚” | 以 stackctl 为唯一环境入口，prod 操作需确认 | 读取 AGENTS + environment skill + stackctl 证据 | `.cursor/commands/deploy.md`、`quwoquan_ops/AGENTS.md` | prod-gray、手写 URL/端口、破坏性 repair 自行执行 | stackctl verify/health/inspect/deploy 报告、回滚证据 | `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile <smoke|integration|release>` |
| `/infra` | “环境巡检 / 拓扑 / 健康检查” | 通过 stackctl 和 manifests 检查环境 | 不创建第二套拓扑或部署脚本 | `.cursor/commands/infra.md`、`environment-ops` skill | 手写 host/port、绕过 manifests | topology/config/packaging/health/inspect 证据 | `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile <smoke|integration|release>` |
| `/obs` | “补观测 / 查指标 / 加告警” | 从业务验收反推指标、日志、trace、SLO 与告警 | 不把日志当完成，要求可查询、可告警、可回滚 | `.cursor/commands/obs.md`、`obs-*.md`、触达区域 AGENTS | 无 SLO、无采样/保留、无 dashboard/report | 指标/日志/trace 字段、告警阈值、查询或看板、三层测试证据 | 触达范围 `verify_*` + `make verify-agent-context-contract` |
| `/rec` | “调推荐 / 补召回排序 / AB 反馈” | 检查信号来源、召回/排序/重排、AB、护栏与回滚 | 不新增双轨标识，不让推荐与行为反馈断链 | `.cursor/commands/rec.md`、`rec-*.md`、相关 acceptance | 缺行为归因、缺冷启动、缺护栏指标 | 推荐策略、反馈归因、AB 分桶、护栏指标、回滚证据 | 推荐专项 gate 或触达范围测试 |
| `/audit` | “全栈审计 / 看代码库健康” | 代码库级发现结构、metadata、特性树和测试漂移 | 不用审计替代特性 `/verify`， findings 必须可定位 | `.cursor/commands/audit.md`、相关 rules/gates | 空泛建议、无文件行号、无修复路径 | Findings、严重度、文件行号、建议验证命令 | `make verify` 或专项审计命令 |
| `/deliver` | “闭环交付这一项” | 串联 `/dev` + `/verify` + `/commit`，先证据后提交 | 不提交未闭环 Story，不用 commit 掩盖缺口 | `.cursor/commands/deliver.md`、`dev/verify/commit` | 无验收、无测试、CR 未闭环 | 实现、Exit Review、门禁、提交准备状态 | 触达范围 gate |
| `/commit` | “提交这轮改动” | 只提交已闭环增量和对应文档/测试/CR | 不提交无证据、旧树口径或手改 generated | `.cursor/commands/commit.md`、acceptance、gate 输出 | 未跑门禁、未说明风险、混入无关改动 | commit scope、验证摘要、剩余风险 | `make verify-agent-context-contract` + 触达范围测试 |
| `crawl` | “跑数据抓取总控 / 内容候选到发布闭环” | 通过 `qwq-data task geo-homepages` 创建唯一 execution 工作包 | 保证来源、五阶段、review、publish、release、ship 走同一主干 | `.cursor/commands/crawl.md`、data skill | mock 产物凑数、版权不清图片、task/batch 双身份、旧输出根 | execution-readiness、output-root-isolation、publish-purity、环境证据 | `python3 quwoquan_data/scripts/cli.py verify content-execution-layout && python3 quwoquan_data/scripts/cli.py verify output-root-isolation` |
| `crawl-topic` | “处理这个对象 / 复核或恢复这个 execution” | 读取 execution manifest 与 evidence，并用原 `geo-homepages` 命令 resume | 同 ID 只 resume；新尝试递增 sequence 并写 retryOf | `.cursor/commands/crawl-topic.md`、data AGENTS | 阶段 runner、taskId/batchId、手写阶段证据、原地改输入 | execution-readiness、失败阶段、重试关系 | `python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <executionId>` |

## Simulation Cases

### Case 1: App 登录错误提示

- 用户输入：“帮我修 App 登录错误提示。”
- 阶段路由：`/dev`，若错误语义或验收不清，先 `/explore` 或 `/prd`。
- Spec Entry：目标是修复登录错误的用户提示与恢复动作；范围在 App 登录入口、runtime mapper、错误码消费；Out of Scope 是不改服务错误契约，除非发现 metadata 缺口。
- 区域规则：`quwoquan_app/AGENTS.md`、runtime error、登录无死循环、Mock 隔离、设计系统。
- Pre-work Reflection：检查是否触发 `errors.yaml`、`CloudException.runtimeFailure`、`RuntimeRecoveryPolicy`、UI l10n、`local_contract` widget/provider、`api_integration` Remote 映射。
- Cursor voice：我会在当前 App workspace 查登录页、mapper、测试和 lints，不手写错误码字符串。
- Codex voice：我会按 AGENTS 层级加载 App 规则，优先用生成错误枚举与验证命令形成证据。
- 出口证据：`local_contract` 覆盖文案/恢复按钮/关闭安全态，必要时 `api_integration` 覆盖 Remote 错误映射。
- 应跑门禁：`dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`、相关 `flutter test`、`make verify-app-login-entry-loop-contract`。

### Case 2: 服务错误码 + App 恢复按钮

- 用户输入：“新增服务错误码并让 App 展示恢复按钮。”
- 阶段路由：`/extend add-errors` -> `/dev` -> `/verify`。
- Spec Entry：目标是新增稳定错误语义与端侧恢复体验；范围包括 metadata、服务 HTTP 边界、App mapper/UI、观测和测试。
- 区域规则：`quwoquan_service/AGENTS.md`、`quwoquan_app/AGENTS.md`、runtime error cutover。
- Pre-work Reflection：必须 metadata-first，禁止只改 UI 或只改服务。
- Cursor voice：我会检查 metadata/codegen、服务 runtime response、App runtime mapper 和测试覆盖。
- Codex voice：我会按 `errors.yaml -> verify/codegen -> RuntimeErrorResponse -> CloudException -> UI -> telemetry -> 三层测试` 链路执行。
- 出口证据：`local_contract` metadata/codegen/mapper/UI，`api_integration` HTTP/Remote 映射，必要时 `user_acceptance` 用户旅程。
- 应跑门禁：`make verify-metadata`、`make codegen`、`make codegen-app`、runtime error cutover。

### Case 3: 内容生产并导入 gamma

- 用户输入：“生产一批内容并导入 gamma。”
- 阶段路由：`data-*` / `crawl` / `/deploy` 环境验证。
- Spec Entry：目标是从数据工程产物到 gamma 可消费样本闭环；范围包括 plan/download/produce/media/verify/ship/importer。
- 区域规则：`quwoquan_data/AGENTS.md`、data skill、`quwoquan_ops/AGENTS.md`。
- Pre-work Reflection：必须 CLI-first、Agent-only 正文、七角色准出、ship sample bundle、service importer 幂等、gamma stackctl 验证。
- Cursor voice：我会读取 `.qwq_output/data/tasks/<executionId>/**` 运行证据、`quwoquan_data/publish/**` 发布真相源与环境 run，不把离线文件生成当完成。
- Codex voice：我会只通过 `python3 quwoquan_data/scripts/cli.py` 和 stackctl 收集证据。
- 出口证据：stage result、gate report、repair report、manifest、review、sample bundle、importer 结果、gamma verify。
- 应跑门禁：`python3 quwoquan_data/scripts/cli.py verify all`、`stackctl verify --env gamma --kind all --profile integration`。

### Case 4: prod-hosted 小流量放量

- 用户输入：“部署 prod-hosted 小流量放量。”
- 阶段路由：`/deploy`，涉及 prod-hosted 需人工确认。
- Spec Entry：目标是 prod rollout stage 放量；范围包括 service image/config、SLO guard、回滚版本、健康检查。
- 区域规则：`quwoquan_ops/AGENTS.md`、environment skill、deploy command。
- Pre-work Reflection：确认不是 `prod-gray`，确认 step/error-rate/p95/redis-error-rate，确认密钥与破坏性动作需人工确认。
- Cursor voice：我会用 stackctl，不手写旧 deploy 脚本。
- Codex voice：我会收集 `.qwq_output/env/prod/runs/**` 和 release state 作为证据。
- 出口证据：stackctl deploy 报告、health/inspect/doctor、回滚路径。
- 应跑门禁：`stackctl verify --env prod --kind all --profile release`。

### Case 5: 检查这一轮是否完成

- 用户输入：“检查这一轮是否完成。”
- 阶段路由：`/verify`，必要时 `/plan-next`。
- Spec Entry：目标是核对本轮目标、规格、任务和验收是否闭环。
- 区域规则：所有触达区域 AGENTS、acceptance、gate 输出。
- Pre-work Reflection：不得用下一轮规划掩盖本轮未完成；检查是否缺三层测试、E2E、观测、门禁。
- Cursor voice：我会读取 diff、测试结果、lints 和 gate 输出。
- Codex voice：我会按 AGENTS 与 workflow 输出通过/缺口/需重跑命令/剩余风险。
- 出口证据：Exit Review 七项、未跑验证原因、下一步只列真实残余风险。
- 应跑门禁：`make verify-agent-context-contract` 以及触达范围专项 gate。

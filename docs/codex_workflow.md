# Codex 工作流接入说明

本文件把仓库现有 `.cursor/commands`、特性树与工程军规，收敛成 Codex 可稳定复用的工作方式。

## 1. 指令分层

Codex 在本机应形成三层加载链：

1. `~/.codex/AGENTS.md`
   用于个人偏好，例如输出语言、沟通风格、通用验证习惯。
2. 仓库根 `AGENTS.md`
   用于全仓统一流程：一棵树、metadata-first、文档刷新、验证门禁。
3. 子目录 `AGENTS.md`
   用于 `quwoquan_app/`、`quwoquan_service/`、`quwoquan_data/` 等局部规则。

原则：全局只放“你个人的通用工作方式”，项目规则只放仓库内，避免跨仓库污染。

详细上下文加载、自然语言路由、规格理解、自检反思与完成后验收复盘，以 `docs/agent_context_contract.md` 为准。本文只保留工作流说明，避免重复维护两套规则。

命令端到端模拟、Cursor/Codex 执行视角、禁止事项、出口证据与最小验证命令，以 `docs/agent_command_simulation_matrix.md` 为准。Codex 处理自然语言输入时，应先把用户话术映射到该矩阵中的命令阶段，再执行对应上下文加载和验证。

Codex voice 固定为：

```text
我按 AGENTS 层级加载上下文：全局偏好 -> 仓库根 -> 子目录；
我把自然语言映射到命令阶段；
我以 Spec Entry / Pre-work Reflection / Exit Review 收口；
我用 CLI、测试和 gate 输出证明完成度。
```

## 2. 把 Cursor 命令映射成 Codex 工作阶段

Codex 不一定认识本仓库的 `/xxx` 命令，但它可以严格遵守这些命令语义。开始任务时，先判断自己属于哪个阶段：

| 阶段 | 何时使用 | 必须产出 |
|---|---|---|
| `/explore` | 需求刚进入、先定位归属 | Journey/Scenario + `L1/L2/L3` + 验收意图 + 三层测试证据 |
| `/prd` | 冻结规格，不做实现 | `spec.md` + `acceptance.yaml` + 必要 registry/CR |
| `/design` | 冻结架构设计 | AppRoot/L1/L2 的 `design.md` |
| `/baseline` | 需求稳定，做一次性冻结 | `spec.md` + `acceptance.yaml` + 必要 `design.md` + CR |
| `/extend` | 实施中需要增量扩 metadata | metadata 变更、verify、codegen、补充手写清单 |
| `/dev` | 正式实现 | Red -> Green -> Refactor + 对应文档/测试回填 |
| `/verify` | 实现后验收 | 对应三层测试证据、gate、测试记录 |
| `/plan-review` | 开发前审规划 | 按多角色刷新规格/验收/任务清单 |
| `/plan-next` | 当前轮完成后再规划 | 完成度复盘、证据对账、下一轮规划 |
| `/continue-dev` | 规划就绪进入开发，或一轮完成后复盘+再规划+再开发 | 裁决最优方案、零技术债、分层测试闭环 + 复盘/遗留风险台账/下一轮规划 |
| `/audit` | 代码库级健康审计 | Findings、严重度、文件行号、修复路径 |
| `/deliver` | 闭环交付 | `/dev` + `/verify` + `/commit` 的证据链 |
| `/commit` | 提交已闭环增量 | Story、文档、metadata/codegen、测试和 CR 对齐 |

建议直接在给 Codex 的 prompt 中写明期望阶段，例如：

```text
先按 /explore 方式定位一棵树归属，不要直接改代码。
```

```text
这是实施阶段，按 /extend add-field -> verify -> codegen -> /dev 执行。
```

```text
先做 /plan-review，补齐规格和验收，再决定是否进入 /baseline。
```

## 3. 需求分解与特性树刷新

### 3.1 起手必答

所有非纯查询任务，都先要求 Codex 写出：

```text
AppRoot Journey/Scenario: <id 或无影响>
L1_domain_service: <domain>
L2_business_capability: <capability>
L3_story: <story>
验收意图: UAT / SIT / GWT / contract
测试证据: local_contract / api_integration / user_acceptance
质量维度: functional / contract / reliability / availability / observability / experience / security / performance / data_consistency
```

起手式前先审视 `docs/outstanding_risks_backlog.md` 的未解决项；若本轮识别出新的长期遗留，需先向用户复述并在确认后登记。

答不出来就先补文档，不准直接写业务代码。

这些字段对应 `docs/agent_context_contract.md` 的 `Spec Entry`。进入实现前还必须完成 `Pre-work Reflection`；完成后必须输出 `Exit Review`。

### 3.2 哪些改动必须同步刷新文档

| 变化类型 | 必改文档 |
|---|---|
| 需求边界、范围、Out of Scope 变化 | 对应层级 `spec.md` |
| 验收口径、测试证据、done_when 变化 | 对应 `acceptance.yaml` |
| 跨领域 Journey/Scenario 新增或迁移 | `specs/feature-tree/journey_scenario_registry.yaml` |
| AppRoot/L1/L2 设计边界变化 | 对应层级 `design.md` |
| 新增/调整特性树节点 | `specs/feature-tree/tree_index.yaml` |
| 形成新一轮可追踪增量 | `specs/changelog/CR-*.yaml` |

### 3.3 特性树校验

涉及特性树结构或验收文档时，优先执行：

```bash
go run ./quwoquan_service/tools/gen_tree_index specs/feature-tree specs/feature-tree/tree_index.yaml
bash quwoquan_ops/gate/scaffold/verify_feature_tree_refactor.sh
bash quwoquan_ops/gate/scaffold/verify_acceptance_standard.sh
```

## 4. 商用品质 Review 门

Codex 每次执行都必须带 review 视角，而不是只按用户指令完成局部代码。Review 优先级如下：

1. 会导致用户旅程断点、数据错乱、安全隐私、生产不可回滚的问题。
2. metadata、DTO、错误码、route/surface/operation、Mock/Remote、测试证据之间的漂移。
3. 缺少三层测试证据、缺少四环境证据、缺少埋点/指标/告警/回滚。
4. 弱类型、硬编码、空 catch、手改 codegen、UI 直连 Mock、第二真相源。
5. 技术债、死代码、过时兼容、无意义 fallback、allowlist 扩张。

任何任务都要按八角色自检：

| 角色 | 必问问题 |
|---|---|
| 产品 | 用户价值是否端到端闭环，是否覆盖主流程、失败、边界、并发和权限态？ |
| 架构 | 是否守住 DDD、单一真相源、抽象克制、存储无关和可回滚演进？ |
| 代码评审 | 是否引入弱类型、硬编码、空 catch、手改 codegen、第二数据通路？ |
| 质量 | Mock/Remote、metadata/codegen、验收、门禁是否一致？ |
| 测试 | `UAT/SIT/GWT/contract` 是否都有 `local_contract/api_integration/user_acceptance` 对应证据？ |
| 用户 | 是否有可理解的加载、空态、错误、权限、降级与性能反馈？ |
| 运维 | 是否有 SLO、指标、采样、告警、日志、TTL、回滚和四环境配置？ |
| 运营 | 是否有曝光、停留、互动、转化、推荐反馈、AB 分桶和归因链？ |

## 5. 四层测试与四环境

### 5.1 三层测试

测试语言必须分清：

- 验收意图：`UAT`、`SIT`、`GWT`、`contract`
- 测试工程层：`local_contract`、`api_integration`、`user_acceptance`
- 非功能质量维度：通过 `quality_facet` 横切到三层测试，不新增第四层目录。

默认映射：

| 层级 | 验收 | 证据 |
|---|---|---|
| AppRoot Journey/Scenario | `UAT` | 主 `user_acceptance`，辅 `api_integration` |
| `L1_domain_service` | 领域边界/治理 | `api_integration/local_contract`，必要时 `user_acceptance` |
| `L2_business_capability` | `SIT` | `api_integration`，辅 `local_contract` |
| `L3_story` | `GWT/contract` | `local_contract`，远端补 `api_integration`，页面补 `user_acceptance` |

远端 API、Repository、MockRepository 或用户旅程变化时：

- `api_integration` 中验证的字段、状态码、错误码、边界行为，必须在 `local_contract` Mock/Provider/Widget/领域规则测试中有对应断言。
- `acceptance.yaml` 不能标记完成却缺 `tests.recorded`。
- 高风险改动必须先有失败测试或明确替代验证说明。
- 异常恢复、性能、安全隐私、可观测、可靠性/可用性、数据一致性适用时必须声明 `quality_facet` 并给出证据；缺证据时返回 `GATE_BLOCK`。

### 5.2 四环境

环境语义固定：

| 环境 | 用途 | 数据源 | 禁止 |
|---|---|---|---|
| `alpha` | 开发/CI | contract-seeded MockRepository | 访问云服务 |
| `beta` | 人工验收 | RemoteRepository + gateway seed | 读取 Dart mock |
| `gamma` | 自动化集成/镜像验证 | RemoteRepository + API seed | 读取 Dart mock |
| `prod` | 生产 | RemoteRepository + 真实数据 | test fixtures / seed / mock |

环境与部署任务必须优先使用 `stackctl`：

```bash
python3 quwoquan_ops/cli/stackctl.py package --env <alpha|beta|gamma|prod>
python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile <smoke|integration|release>
python3 quwoquan_ops/cli/stackctl.py health --target <target> --scope full
python3 quwoquan_ops/cli/stackctl.py inspect --target <target> --kind all
```

生产没有 `prod-gray` 环境；灰度是 `prod` 的 rollout stage。涉及 prod-hosted 放量、回滚版本、密钥、hosted URL 或破坏性 repair 时，必须停下请求人工确认。

## 6. 可观测、可配置与推荐闭环

新增或修改用户可见能力时，默认补齐：

- 页面：曝光、停留、异常、关键交互；内容消费页还要有消费深度和互动。
- API：请求量、错误率、延迟 histogram、业务失败原因、trace/request id。
- 推荐：离线指标、在线指标、护栏指标、feedback attribution、特征投影与回滚开关。
- 配置：配置来源、环境覆盖、默认值、灰度范围、回滚路径、不可用降级。
- 告警：SLI/SLO、阈值、采样率、保留周期、仪表盘或报告位置。

内容与推荐链路必须端到端无断点：

```text
数据工程 plan/download/produce/media/verify/ship
  -> publish sample bundle / importer
  -> metadata/codegen/RemoteRepository
  -> 用户发现/搜索/详情/消费/互动
  -> 行为事件与 referral/feedRequestId/traceId
  -> 推荐 HotPath / 特征工程 / AB 分桶
  -> 指标、告警、运营分析与下一轮内容/推荐优化
```

如果某段链路没有契约、测试、观测或回滚说明，不能宣称完成。

## 7. 错误码端云一体化

错误码是端云产品语义，不是技术实现细节。任何新增或修改错误、权限、降级、重试、超时、风控、限流、校验失败、第三方失败，都必须按同一条链路处理：

```text
quwoquan_service/contracts/metadata/**/errors.yaml
  -> verify/codegen
  -> 服务端 RuntimeErrorResponse
  -> HTTP status + stable code + requestId/traceId + context.attributes
  -> App CloudException/runtime mapper
  -> RuntimeFailure + RuntimeRecoveryPolicy
  -> 用户可见提示/操作按钮/降级 UI
  -> telemetry/log/metrics/alert/dashboard
  -> local_contract/api_integration/user_acceptance 证据
```

硬约束：

- 错误码唯一定义于 metadata `errors.yaml`，包含 stable code、HTTP status、`user_message.zh/en` 或 l10n key、`recovery.action`、`disruptionLevel`、Go/Dart 常量。
- 稳定 code 使用 `MODULE.KIND.REASON`，不要把动态字段、用户输入、第三方原始错误拼进 code；上下文进入 string-only `context.attributes`。
- 服务端 HTTP 边界必须通过 runtime errors helper 输出 `RuntimeErrorResponse`，保留 request id、trace id、operation id、surface/context，不返回自造错误 JSON。
- App 端 `CloudException` 必须由 runtime mapper 生成并暴露 `runtimeFailure`；UI/Provider 消费 `RuntimeFailure` 或 `runtimeErrorDisplayMessage`，不展示 raw exception/debugMessage。
- 用户提示必须来自 codegen 错误枚举、`toDisplayMessage(context.l10n)`、`UITextConstants` 或 l10n；禁止在 UI switch/case 里硬编码错误码字符串或中文文案。
- 恢复行为不存成错误码事实；通过 `RuntimeRecoveryPolicy` 表达重试、稍后再试、登录、权限设置、联系客服、降级展示、静默恢复等动作。
- 对用户隐藏 debug detail，但观测链路必须记录 code、domain、operation、surface、recovery action、disruption level、request/trace id、环境、版本、采样策略。
- 告警与 SLO 必须按错误族和影响等级聚合：用户可恢复错误、权限/登录错误、业务校验错误、第三方依赖错误、服务不可用错误、数据一致性错误要有不同阈值和处理路径。
- 四环境必须验证错误语义一致：alpha 覆盖 Mock/fixture，beta/gamma 覆盖 Remote/API seed，prod 只保留真实观测与灰度/回滚证据。

测试要求：

- `local_contract`：metadata semantic、错误码枚举/codegen、硬编码扫描、runtime cutover check、mapper、Provider/UI 状态、Mock 错误响应。
- `api_integration`：服务 HTTP 边界、真实 API 错误响应、request/trace id 透传、RemoteRepository 映射。
- `user_acceptance`：用户旅程中错误出现后的提示、恢复、降级、埋点和告警证据。

常用验证：

```bash
make verify-metadata
make codegen
make codegen-app
dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
```

如果只改了 UI 文案但没有 metadata/codegen，如果只改了服务错误但没有端侧 mapper/UI，如果只有日志没有用户恢复路径，均视为未完成。

## 8. 零技术债与不兼容错误实现

当前阶段按未上线处理，优先交付商用干净版本：

- 不为不合理实现保留兼容分支、shim、fallback、adapter 或 allowlist。
- 发现错误抽象、第二真相源、死代码、重复链路时，优先替换或删除，而不是继续包一层。
- 不允许“先绕过门禁”“后续补测试”“临时兼容旧数据”作为完成定义。
- TODO/FIXME、`@Deprecated`、注释掉的大段旧代码、测试放宽阈值，默认视为未完成。
- 只有已发布、持久化、外部稳定接口才讨论兼容；未上线分支内的错误实现直接改正。

## 9. 契约优先与 metadata-first

Codex 在本仓库应默认遵守：

1. 先改 `quwoquan_service/contracts/metadata/**`
2. 运行 verify
3. 运行 codegen / codegen-app
4. 再写手工业务逻辑
5. 最后补测试与 gate

遇到以下情况，优先走 metadata 而不是直接改实现：

- 新字段
- 新错误码
- 新 API path / operation
- 新 route / surface
- 新 DTO 契约

常用校验命令：

```bash
make verify-metadata
make codegen
make codegen-app
make gate
```

## 10. 设计系统与前端约束

在 `quwoquan_app/` 内，Codex 必须默认认为以下约束是硬约束，而不是“风格建议”：

- 颜色使用 `AppColors.*`
- 间距/尺寸使用 `AppSpacing.*`
- 字体使用 `AppTypography.*`
- 静态文案使用 `UITextConstants.*` 或 `l10n`
- Repository 通过 Provider 装配，不能在 UI 里直连 Mock/Remote
- 页面改动要检查页面横向质量矩阵与相关 gate

具体规则不要硬背，进入 `quwoquan_app/` 后读取该目录下的 `AGENTS.md`，再按触达路径补读相关 `.cursor/rules/*.md`。

## 11. 数据工程闭环

数据工程不是脚本集合，而是内容供给到产品消费的生产线。Codex 处理 `quwoquan_data/` 时必须遵守：

- 唯一入口是 `python3 quwoquan_data/scripts/cli.py <command>`，禁止新增孤立可执行业务脚本。
- 标准链路是 `plan -> download -> produce compose-brief -> Agent semantic -> produce review/materialize -> media check-images -> verify -> ship`。
- CLI 只负责 IO、契约、拉取、打分、校验、落盘；正文语义创作由 Agent 基于 `writing_pack.json` 和 `prompt.md` 写回。
- 每个 stage 必有 stage result、gate report、repair report；失败必须按 fallback stage 回退，不允许原地反复硬改。
- 内容必须满足来源权利、事实可回溯、图片安全、实体/标签对齐、发布账本、人审状态、环境采样与服务 importer 证据。
- 数据工程产物最终必须能被端侧用户消费、被行为反馈追踪、被推荐系统消费，不能停在离线文件层。

## 12. 推荐给 Codex 的提示词模板

### 12.1 需求进入

```text
先按 /explore 执行：定位这项需求对应的 Journey/Scenario、L1/L2/L3、验收意图和三层测试证据，若不完整就先补规格，不要直接实现。
```

### 12.2 规格冻结

```text
先按 /plan-review 检视现有 spec/acceptance 是否满足八角色、三层测试、四环境、错误码端云链路、可观测、推荐反馈和零技术债约束；如果收敛，再按 /baseline 更新 spec、acceptance、必要 design 和 CR。
```

### 12.3 实施阶段

```text
这是实施阶段。若涉及字段/错误码/path/route/surface，请先按 /extend 的语义走 metadata-first，再进入 /dev；完成后按 /verify 回填证据。
```

### 12.4 收口与下一轮规划

```text
先按 /verify 对账当前改动的三层测试、四环境、错误码链路、观测、推荐反馈和部署证据，再按 /plan-next 生成下一轮规划，不能用新规划掩盖未完成项。
```

若本轮关闭了 backlog 中的遗留事项，收口前必须同步更新 `docs/outstanding_risks_backlog.md` 的 checkbox、状态与验证证据。

### 12.5 错误码/异常语义任务

```text
这是错误码端云链路任务。先从 metadata errors.yaml 定义 code/user_message/recovery/disruptionLevel，verify/codegen 后同步服务 RuntimeErrorResponse、App CloudException/runtime mapper、UI 用户提示、telemetry/metrics/alert 和三层测试证据。
```

### 12.6 数据工程任务

```text
按 quwoquan_data CLI-first 执行：先 plan/download/compose-brief，正文只由 Agent 基于 writing_pack/prompt 创作，再 review/materialize/media/verify/ship；每阶段必须有 gate report 和 repair report。
```

## 13. 配置建议

本机 `~/.codex/config.toml` 至少包含：

```toml
project_doc_max_bytes = 65536
project_doc_fallback_filenames = ["TEAM_GUIDE.md", ".agents.md"]
```

这样 Codex 可以安全加载根 `AGENTS.md` + 子目录 `AGENTS.md`，并为后续补充备用文件名留出空间。

若本机 Codex 版本支持，可用以下方式检查实际加载链：

```bash
codex --print-instructions
```

## 14. 维护原则

- 尽量把稳定规则写进最近的 `AGENTS.md`，不要把大量一次性说明塞进 prompt。
- 规则要短、可执行、可验证；细节放到现有 `specs/`、`quwoquan_service/contracts/metadata/`、`.cursor/rules/` 文档。
- 如果 Codex 某个误判反复出现，修 `AGENTS.md` 或补 gate，而不是反复口头纠正。

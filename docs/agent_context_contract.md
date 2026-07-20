# Agent Context Contract

本文定义 Cursor/Codex 在本仓库的上下文加载、规格理解、自检反思和验收复盘契约。无论用户使用 slash command，还是直接输入自然语言，Agent 都必须进入同一套工程要求。

## 0. Agent Execution Protocol

本协议是 Cursor/Codex 每次 vibe coding 或显式命令输入的执行骨架。Agent 不得只把用户输入解释为“改几个文件”，而必须先把输入转成可验收的工程任务。

### 0.1 Spec Entry

执行前必须形成最小规格入口：

```text
Spec Entry
目标：
用户价值：
范围：
Out of Scope：
AppRoot Journey/Scenario：
L1_domain_service：
L2_business_capability：
L3_story：
验收意图：UAT / SIT / GWT / contract
测试证据：local_contract / api_integration / user_acceptance
质量维度：functional / contract / reliability / availability / observability / experience / security / performance / data_consistency
风险：
```

形成 `风险` 前，先对照 `docs/outstanding_risks_backlog.md` 的未解决项；若出现新的长期遗留，需先向用户复述并在确认后登记。

如果无法填写关键项，Agent 必须先切回 `/explore`、`/prd` 或 `/plan-review`，不得进入实现。

### 0.2 Pre-work Reflection

实施前必须完成执行前反思：

```text
Pre-work Reflection
是否触发 metadata-first：
是否触发 runtime error / errors.yaml：
是否触发 mock 隔离 / env-seed-first：
是否触发页面质量 / 设计系统：
是否触发 data CLI-first / Agent-only 正文：
是否触发 stackctl / 四环境：
是否跨 App / Service / Data / Ops / Portal：
是否需要 E2E 证据：
是否存在第二真相源、旧兼容、allowlist 或测试放宽：
是否触发异常恢复、性能、安全隐私、埋点/日志/指标、数据一致性等非功能质量维度：
```

任一项为“是”时，必须加载对应区域 `AGENTS.md`、`.cursor/rules`、`.cursor/commands` 或 skill。

### 0.3 自然语言等价 / Command Execution

自然语言与 slash command 等价。Agent 根据意图选择命令阶段：

- “看看怎么做 / 归属哪里 / 风险是什么” -> `/explore`
- “冻结需求 / 写规格 / 明确验收” -> `/prd`
- “设计方案 / 架构边界 / 回滚观测” -> `/design`
- “需求稳定 / 做基线” -> `/baseline`
- “新增字段 / 错误码 / API / UI 配置” -> `/extend`
- “实现 / 修复 / 开始写代码” -> `/dev`
- “检查 / 收口 / 验一下” -> `/verify`
- “部署 / 发布 / 放量 / 回滚” -> `/deploy`
- “环境 / 拓扑 / 健康检查 / 巡检” -> `/infra`
- “观测 / 指标 / 日志 / trace / 告警” -> `/obs` 或 `obs-*`
- “推荐 / 召回 / 排序 / AB / 反馈回流” -> `/rec` 或 `rec-*`
- “全栈审计 / 结构健康 / 代码库一致性” -> `/audit`
- “闭环交付 / dev verify commit 一起做” -> `/deliver`
- “提交已闭环增量” -> `/commit`
- “内容生产 / 数据工程 / 抓取 / 导入” -> `data-*` 或 `crawl*`

命令模拟与出口证据见 `docs/agent_command_simulation_matrix.md`。

### 0.4 Exit Review

完成后必须输出或回填出口验收：

```text
Exit Review
规格达成：
测试证据：
E2E 验证：
产品/UX：
运营观测：
自动化/门禁：
剩余风险：
```

若本轮关闭或新增了长期遗留/风险，必须同步更新 `docs/outstanding_risks_backlog.md`。

不适用项必须说明原因；禁止只输出“修改了哪些文件”。

### 0.5 Agent Voice

Cursor voice：

- 我在当前 workspace 内执行，优先读取仓库根 `AGENTS.md`、触达路径最近的 `AGENTS.md`、相关 `.cursor/rules` 和 `.cursor/commands`。
- 我会在动手前说明 Spec Entry 与 Pre-work Reflection；动手后按 Exit Review 回收证据。
- 我会保护脏工作树，不回滚用户无关改动，不手改 generated 文件，不绕过 gate。

Codex voice：

- 我按 AGENTS 层级加载上下文：全局偏好 -> 仓库根 -> 子目录。
- 我把自然语言输入映射到本仓库命令阶段，并优先用 CLI/gate 形成可复验结果。
- 我用验证命令、测试路径、门禁输出和剩余风险说明完成度，而不是只给代码摘要。

## 1. 输入路由

每次非纯查询输入都按以下顺序处理：

```text
user input
  -> stage route
  -> feature tree route
  -> area route
  -> spec understanding
  -> pre-work reflection
  -> implementation or doc refresh
  -> post-work acceptance reflection
```

### 1.1 阶段路由

| 用户意图 | 阶段 | 读取入口 |
|---|---|---|
| 只想澄清范围、定位归属、问“该怎么做” | `/explore` | `.cursor/commands/explore.md` |
| 冻结用户价值、范围、Out of Scope、验收 | `/prd` | `.cursor/commands/prd.md` |
| 冻结架构、边界、依赖、回滚和观测 | `/design` | `.cursor/commands/design.md` |
| 需求稳定后一次冻结规格、验收、必要设计和 CR | `/baseline` | `.cursor/commands/baseline.md` |
| 实施中新增字段、错误码、API、事件、UI 配置 | `/extend` | `.cursor/commands/extend.md` |
| 正式实现 | `/dev` | `.cursor/commands/dev.md` |
| 实现后复核证据 | `/verify` | `.cursor/commands/verify.md` |
| 开发前多角色审规划 | `/plan-review` | `.cursor/commands/plan-review.md` |
| 完成后生成下一轮规划 | `/plan-next` | `.cursor/commands/plan-next.md` |
| 代码库级健康审计 | `/audit` | `.cursor/commands/audit.md` |
| 闭环交付 | `/deliver` | `.cursor/commands/deliver.md` |
| 提交已闭环增量 | `/commit` | `.cursor/commands/commit.md` |
| 可观测、推荐、数据工程、环境部署 | 专项阶段 | `.cursor/commands/obs-*.md`、`rec-*.md`、`data-*.md`、`infra*.md`、`deploy.md` |

用户没有输入 slash command 时，Agent 必须根据自然语言自动选择等价阶段。

### 1.2 区域路由

| 触达路径或意图 | 必读上下文 | 关键约束 |
|---|---|---|
| `quwoquan_app/**` | `quwoquan_app/AGENTS.md`、Dart/Mock/runtime error/page quality rules | 设计系统、Provider、Mock/Remote、错误体验、页面矩阵、四环境数据源 |
| `quwoquan_service/**` | `quwoquan_service/AGENTS.md`、metadata README、架构/runtime error rules | metadata-first、DDD、RuntimeErrorResponse、`api_integration` 真实存储、metrics/trace/SLO |
| `quwoquan_data/**` | `quwoquan_data/AGENTS.md`、`quwoquan-data-content` skill | CLI-first、Agent-only 正文、事实/权利/图片/账本、ship/importer、七角色准出 |
| `quwoquan_ops/**`、环境、部署、门禁 | `quwoquan_ops/AGENTS.md`、`environment-ops` skill | stackctl、四环境、repair 白名单、prod rollout、gate 证据 |
| `quwoquan_ops/portal/**` | `quwoquan_ops/portal/AGENTS.md` | NodeNext imports、runtime errors、观测页面、test/build |
| 跨多个区域 | 本文 E2E 模式 | 不得局部完成，必须补端到端证据 |

## 2. 正向规格理解

上下文加载完成后，Agent 必须先把任务翻译成正向规格，而不是直接列文件或动手实现。

最小自检：

```text
目标：
用户价值：
范围：
Out of Scope：
AppRoot Journey/Scenario：
L1_domain_service：
L2_business_capability：
L3_story：
验收意图：UAT / SIT / GWT / contract
测试证据：local_contract / api_integration / user_acceptance
质量维度：functional / contract / reliability / availability / observability / experience / security / performance / data_consistency
风险：
```

如果无法填写关键项，先进入 `/explore`、`/prd` 或 `/plan-review`，不得直接实现。

## 3. 执行前反思

实施前必须确认：

- 是否触发 metadata-first、env-seed-first、mock 隔离、页面质量、runtime error、数据工程 CLI-first、环境部署或推荐/观测规则。
- 是否触发异常恢复、性能、安全隐私、埋点/日志/指标、数据一致性等非功能质量维度；适用但无测试证据时必须返回 `GATE_BLOCK`。
- 是否需要更新 `spec.md`、`design.md`、`acceptance.yaml`、`journey_scenario_registry.yaml`、`tree_index.yaml` 或 `specs/changelog/CR-*.yaml`。
- 是否涉及错误码端云链路：`errors.yaml -> codegen -> RuntimeErrorResponse -> CloudException/runtime mapper -> UI prompt -> telemetry/alert -> local_contract/api_integration/user_acceptance`。
- 是否会跨 App、Service、Data、Ops 任意两个以上区域。
- 是否存在错误实现、旧兼容、allowlist 扩张、测试阈值放宽或第二真相源；当前未上线阶段默认直接修正，不做兼容。

## 4. 跨域 E2E 模式

只要输入涉及端云、数据入库、内容消费、推荐反馈、环境部署、可观测或错误码全链路，就启用 E2E 模式：

```text
Data
  -> Service
  -> App
  -> Behavior
  -> Recommendation
  -> Observability
  -> Environment
```

E2E 准出：

- `Data`：内容、实体、标签、素材、账本、sample bundle、service importer 可追溯，并满足 `quwoquan_data/AGENTS.md` 的数据工程七角色准出。
- `Service`：metadata、API、RuntimeErrorResponse、真实存储、metrics、trace、SLO、回滚。
- `App`：Repository/Provider/UI、设计系统、错误提示、四态、Mock/Remote 一致。
- `Behavior`：`referralSource`、`feedRequestId`、trace/request id、互动反馈完整。
- `Recommendation`：HotPath、特征投影、AB 分桶、护栏指标、回滚开关。
- `Observability`：曝光、停留、互动、错误、延迟、freshness/correctness、dashboard/report。
- `Environment`：alpha/beta/gamma/prod 数据源、包纯度、topology，以及按证据级别执行 `stackctl verify --profile smoke|integration|release`；`baseline` 不连接环境。

跨域任务至少需要 `local_contract` 与 `api_integration`；用户旅程或发布前能力必须补 `user_acceptance`。

## 5. 完成后验收复盘

最终响应或对应验收文档必须覆盖适用项：

| 视角 | 必答 |
|---|---|
| 规格达成 | 是否满足目标、范围、Out of Scope 和成功标准 |
| 测试证据 | `local_contract/api_integration/user_acceptance` 跑了什么，未跑说明原因 |
| E2E 验证 | Data/Service/App/Behavior/Recommendation/Observability/Environment 是否闭环 |
| 产品/UX | 加载、空态、错误态、权限态、恢复动作、设计系统是否满足 |
| 运营观测 | 指标、SLO、告警、采样、dashboard/report、归因链是否可用 |
| 自动化/门禁 | gate、CLI、stackctl、repair/fallback、无人值守能力是否覆盖 |
| 剩余风险 | 是否存在技术债、旧兼容、allowlist、未挂载脚本、未完成证据 |

不适用项要说明原因。禁止只输出“改了哪些文件”。

非功能质量维度必须单独说明：异常/恢复、性能、安全/隐私、可观测、可靠性/可用性、数据一致性。任何适用项缺少 `local_contract`、`api_integration` 或 `user_acceptance` 的合理证据时，最终结论必须是 `GATE_BLOCK`，不得用“后续补”或单纯人工确认代替。

## 6. Rules / Commands / Skills / MCP / Gates 分工

- `AGENTS.md`：跨工具可迁移的主干，负责项目身份、阶段模型、不可谈判约束和区域入口。
- `.cursor/rules/*.mdc`：短小、稳定、可作用域化的硬规则；使用 `alwaysApply`、`globs`、`description` 控制加载。
- `.cursor/commands/*.md`：显式 slash workflow，说明阶段准入、产出和阻断。
- `.cursor/skills/**/SKILL.md`：重复多步能力，例如数据生产、环境运维、异常 triage。
- MCP：外部系统和实时数据入口；AGENTS 只说明何时使用，不复制外部知识。
- Gates/Hooks/CI：强制执行层；AI 指令只负责 steering，不能替代门禁。

## 7. 上下文预算与规则债

维护要求：

- 根 `AGENTS.md` 保持瘦身，复杂流程进入本文或 skill。
- 单个 `.cursor/rules/*.mdc` 尽量一个主题，避免复制大段 docs。
- 新增长期规则必须有适用范围、权威来源、禁止项、必跑门禁。
- 定期清理重复规则、旧入口、过期 allowlist、测试阈值放宽、无 owner 技术债。

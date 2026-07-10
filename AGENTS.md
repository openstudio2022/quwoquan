# quwoquan Codex Guide

本仓库为 Codex 提供分层指令。进入任一子目录工作时，先读取本文件，再读取当前工作目录路径上更近的 `AGENTS.md`。

## 每次任务的起手式

对所有非纯查询任务，先按 `docs/codex_workflow.md` 的命令语义判断当前处于哪一阶段：

- `/explore`
- `/prd`
- `/design`
- `/baseline`
- `/extend`
- `/dev`
- `/verify`
- `/plan-review`
- `/plan-next`

开始实现前，必须先明确并在工作说明中自检：

- `AppRoot Journey/Scenario`
- `L1_domain_service`
- `L2_business_capability`
- `L3_story`
- 验收意图：`UAT / SIT / GWT / contract`
- 测试证据：`local_contract / api_integration / user_acceptance`

如果以上任一项无法明确，先刷新规格或特性树文档，不要直接写实现。

## 遗留事项与风险待办

- 所有非纯查询任务开始前，先审视 `docs/outstanding_risks_backlog.md` 的未解决项，判断是否与当前任务直接相关、是否需要一并收口。
- 发现新的长期遗留或风险时，先向用户复述事项、原因和影响；只有用户确认后，才能把它登记到 backlog。
- 解决 backlog 中已有事项时，必须同步回写状态、日期与验证证据；禁止只在会话里口头说明“已修复”而不打勾。
- 禁止维护第二套遗留事项清单；正式遗留与风险只记录在 `docs/outstanding_risks_backlog.md`。

## 必读真相源

1. `specs/00_MASTER_DEVELOPMENT_FLOW.md`
2. `specs/feature-tree/README.md`
3. `specs/feature-tree/journey_scenario_registry.yaml`
4. `specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md`
5. `quwoquan_service/contracts/metadata/README.md`
6. `docs/agent_context_contract.md`
7. `docs/agent_command_simulation_matrix.md`
8. `docs/codex_workflow.md`

只有在任务相关时，再继续读取对应 `.cursor/commands/*.md` 与 `.cursor/rules/*.md`，避免一次性灌入无关规则。

## 自然语言与命令等价

用户直接输入自然语言时，也必须按 `docs/agent_context_contract.md` 路由：先识别阶段、特性树、触达区域和三层测试证据，再做正向规格理解与执行前自检反思。不能因为用户没有显式输入 `/explore`、`/dev` 或 `/verify` 就跳过项目规约。

触达多个区域（App / Service / Data / Ops / Portal）时，必须自动启用端到端模式，证明 `Data -> Service -> App -> Behavior -> Recommendation -> Observability -> Environment` 无断点。

每次非纯查询任务必须显式遵守三段协议：

- **Spec Entry**：目标、用户价值、范围、Out of Scope、特性树、验收意图、三层测试证据、风险。
- **Pre-work Reflection**：metadata-first、runtime error、mock 隔离、页面质量、data CLI-first、stackctl、跨域 E2E 是否触发。
- **Exit Review**：规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁、剩余风险。

命令端到端模拟和 Cursor/Codex 执行语气见 `docs/agent_command_simulation_matrix.md`。不允许“只改文件、无验收、无测试、无风险说明”。

## 商用品质默认门

Codex 在本仓库做任何增量，都必须同时用这些视角审视，不得只完成代码表面改动：

- **Review 视角**：按产品、架构、代码评审、质量、测试、用户、运维、运营八角色检查；优先发现 bug、契约漂移、无测试、无观测、体验断点、第二真相源和不合理抽象。
- **三层测试视角**：`local_contract`、`api_integration`、`user_acceptance` 必须与 `UAT/SIT/GWT/contract` 映射；远端行为在 `api_integration` 中验证的字段、错误码和边界，必须能在 `local_contract` 的 Mock/Provider/Widget/领域规则中找到对应覆盖。
- **四环境视角**：`alpha`、`beta`、`gamma`、`prod` 的数据源、配置、包纯度、URL/topology、部署与回滚证据必须分层；不存在 `prod-gray`，生产灰度只是 `prod` rollout stage。
- **错误码端云链路视角**：错误码、用户提示、恢复动作、HTTP 响应、端侧 `CloudException`/`RuntimeFailure`、埋点、日志、告警和测试必须同源；禁止只改 UI 文案、只改 mapper 或只改服务错误响应。
- **可观测与可配置视角**：新增页面、API、行为信号、推荐策略、数据工程发布都必须声明 SLI/SLO、指标、采样、保留周期、告警阈值、配置来源、灰度与回滚。
- **端到端闭环视角**：从数据工程两条内容生产线、素材/实体/标签治理、内容入库、用户发现与消费、互动反馈、推荐特征回流、运营分析和四层监控，链路不得有断点。

任何一项无法证明，应先返回 `GATE_BLOCK` 并补规格、契约、测试或运维证据。

## 文档刷新规则

- 需求归属不清：先按 `/explore` 补树归属。
- 规格或验收变化：更新对应 `spec.md` 与 `acceptance.yaml`。
- 跨领域 Journey/Scenario 变化：更新 `specs/feature-tree/journey_scenario_registry.yaml`。
- AppRoot / `L1_domain_service` / `L2_business_capability` 设计变化：更新对应 `design.md`；`L3_story` 禁止新增 `design.md`。
- 形成可追踪增量：补 `specs/changelog/CR-*.yaml`。
- 调整特性树节点后：重建 `specs/feature-tree/tree_index.yaml` 并跑对应校验。
- 触及错误码、权限/异常语义、用户提示、恢复策略或服务 HTTP 边界：同步刷新 metadata `errors.yaml`、codegen、端侧 mapper/UI、服务响应、观测指标与测试证据。
- 触及推荐、观测、环境部署或内容生产闭环：同步刷新对应能力/Story 的 `acceptance.yaml` 证据、CR 与必要的 `design.md`，不得只改实现。
- 发现新的长期遗留/风险且用户确认后：追加 `docs/outstanding_risks_backlog.md`。
- 关闭已有遗留/风险事项：同步更新 `docs/outstanding_risks_backlog.md` 的状态、日期与验证证据。

## 编码总约束

- `quwoquan_service/contracts/metadata/**` 是字段、错误码、path、route、surface、operation、decoder context 的唯一真相源。
- `quwoquan_service/contracts/metadata/**/errors.yaml` 是错误码、用户可见提示、恢复动作和端云错误语义的唯一真相源；稳定错误码使用 `MODULE.KIND.REASON`，上下文只进 string-only `context.attributes`。
- 先 metadata，后 verify/codegen，再写业务逻辑；禁止手改 codegen 产物。
- 不维护第二套路由、错误码、UI IA、mock 数据或特性树。
- 当前阶段按未上线处理：对不合理实现零兼容、零技术债容忍，优先替换为正确契约与正确架构；禁止为错误实现继续加 shim、fallback、allowlist 或旁路。
- 禁止以“后续补”“临时兼容”“测试先放宽”“先绕过 gate”为交付策略；无法闭环就明确阻断。
- 仓库长期分支只允许 `dev1.0` 与 `main`；未经用户明确同意，不得创建、提交或推送其他分支。若确需例外，先更新 `quwoquan_ops/policies/branch_policy.yaml` 再执行。
- 脏工作树是常态；禁止回滚或覆盖与你当前任务无关的用户改动。
- 优先做可验证的小改动，并执行与触达范围匹配的 gate/test。

## 工作方式

- 输出与注释默认使用中文；代码标识符、命令、路径保持原文。
- 完成任务时，不只说明改了哪些文件；必须按适用项说明规格达成、测试证据、E2E 验证、产品/UX、运营观测、自动化/门禁和剩余风险。
- 若用户纠正了反复出现的项目约束，把稳定规则补到离作用域最近的 `AGENTS.md` 或长期文档里，而不是只记在当前会话。

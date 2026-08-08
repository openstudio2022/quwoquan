# L3 Story：环境运营 CLI 与 Skill (`environment-ops-cli-and-skill`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为操作测试或生产环境的工程角色，
我希望通过 `stackctl` 执行可重复的打包、启动、健康、验证与部署动作，并得到稳定 JSON 结果，
从而让人工和 Agent 使用同一环境操作入口。

## 2. 范围与非目标

### In Scope

- “环境运营 CLI 与 Skill”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 环境运营 CLI 与 Skill

- `stackctl` 必须输出稳定 JSON 报告，并在 `.qwq_output/env/<env>/runs/<run-id>/` 归档 Markdown 摘要。

<a id="req-002"></a>
### REQ-002 Cursor、CLI、CI、workflow 与 project skill 必须共享同一套 stackctl 子命令，不得复制第二套检查/部署逻辑

- Cursor、CLI、CI、workflow 与 project skill 必须共享同一套 `stackctl` 子命令，不得复制第二套检查/部署逻辑。
- `stackctl` 必须输出稳定 JSON 报告，并在 `.qwq_output/env/<env>/runs/<run-id>/` 归档 Markdown 摘要。
- `stackctl` 必须支持 `local / ssh-hosted / workflow` 三类执行后端。
- 日常开发冷/热启动只允许由 `stackctl dev-session` 从当前工作树实时编排；单 target 与 `--all-nonprod` 都必须分别返回 compile/launch、mutable warnings、health、session kind、target identity 与报告引用。
- Prod `stackctl up` 继续只消费 active candidate；Alpha/Beta/Gamma test-live 不读取 immutable candidate。App launcher 继续只读预检，Cursor、Make、CI 与 Skill 不得复制环境编排。
- `inspect` 统一覆盖 `logs / network / data / metrics / config / security`。
- gamma / prod 发布必须通过 `stackctl deploy` 暴露统一入口，底层可复用既有 workflow 与 `config_release_*` 脚本。
- skill 遇到登录、审批、密钥、生产破坏性动作时必须显式停下并请求人工确认。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 环境运营 CLI 与 Skill

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“环境运营 CLI 与 Skill”对应的公开行为。
- THEN `stackctl` 必须输出稳定 JSON 报告，并在 `.qwq_output/env/<env>/runs/<run-id>/` 归档 Markdown 摘要。
- AND `dev-session` 的 render、compile/launch、up、health 与 handoff 具有可独立定位的 phase 结果；source/config 漂移只告警，三环境入口严格串行且 runtime health 失败不覆盖编译结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-config`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 环境运营 CLI 与 Skill 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“环境运营 CLI 与 Skill”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

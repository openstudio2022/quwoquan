# L3 Story：配置 Provider 分层 (`config-provider-layering`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod/`，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “配置 Provider 分层”的输入、可观察主路径、失败语义以及与父能力的交接。
- sys/ops 配置定义与覆盖。
- alpha/beta/gamma/prod 环境约束。
- topology 到 deploymentRef 的闭环。
- process-domain 和 module-package 登记。
- 第五环境或旧目录兼容。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 配置 Provider 分层

- 统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod/`。

<a id="req-002"></a>
### REQ-002 统一目录结构：default/ + alpha/ + beta/ + gamma/ + prod/

- 统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod/`
- 统一覆盖顺序：默认配置 -> 环境配置 -> 环境变量覆盖。
- 统一部署映射：`environments -> deploy process -> domains`
- 统一 environment topology：受支持环境分别由 `<env>/runtime.yaml` 声明运行策略，workload 从各服务环境部署目录推导；四环境 App composition 均为 Remote，alpha 只通过容量、endpoint、访问控制、release 与第三方 sandbox 策略差异化。
- 统一环境包策略：App/Service 包的 host allowlist、secret scope 与 purity gate 由环境 runtime 驱动；production App composition 固定 Remote，不作为环境可切换字段。
- 统一自动化入口：环境打包、校验、健康检查与巡检统一经 `stackctl` 暴露机器可读报告。
- `alpha` 的 topology 字段必须完整，不能通过缺字段表达“简化环境”。
- `prod` 只允许 `artifactPolicy.app.runtimeEnv=prod`，禁止任何 `prod-gray` 目录或枚举。
- 本地 profile 与 host 端口必须来自 `quwoquan_ops/environments/local_env_port_manifest.yaml`，不得散落在脚本内作为官方默认值。
- `prod` 环境必须显式设置 `APP_ENV=prod`

<a id="req-003"></a>
### REQ-003 必须metadata 配置定义、四环境覆盖与唯一 workload topology 的单轨闭环，且失败时不得写入成功事实

- 系统必须metadata 配置定义、四环境覆盖与唯一 workload topology 的单轨闭环，且失败时不得写入成功事实。

<a id="req-005"></a>
### REQ-005 配置目录统一：default/alpha/beta/gamma/prod

- 配置目录统一：default/alpha/beta/gamma/prod。
- 覆盖规则统一：default -> APP_ENV -> env var。
- 生产挂载统一：`CONFIG_ROOT=/etc/qwq-config`
- `APP_ENV` 仅允许 `alpha|beta|gamma|prod`
- 版本配置文件不可变，发布后禁止覆盖写入。

<a id="req-006"></a>
### REQ-006 四环境配置与拓扑无漂移

- 删除输出目录后仍可从受控真相源重建快照。

<a id="req-007"></a>
### REQ-007 环境集合严格为 alpha/beta/gamma/prod；dev、integration、prod-gray 不得作为环境目录或运行值

- 环境集合严格为 `alpha/beta/gamma/prod`；`dev`、`integration`、`prod-gray` 不得作为环境目录或运行值。
- secret 只能引用，不得写明文。
- UI 动态配置归对象级 `ui_config.yaml`，不得混入 `sys.*`/`ops.*`。
- workload 的实际部署入口必须与 topology 的 `deploymentRef` 闭环。

<a id="req-008"></a>
### REQ-008 热更新仅适用于低风险配置字段，禁止覆盖高风险连接/鉴权类字段

- 热更新仅适用于低风险配置字段，禁止覆盖高风险连接/鉴权类字段。
- 公共库抽象必须保持现有服务启动语义兼容。
- 任何演进项必须保持 `default -> env -> version -> env vars` 基线不变。

## 4. 契约引用

- canonical：`APP_ENV`
- canonical：`CONFIG_VERSION`
- canonical：`quwoquan_service/control-plane/platform-ops/config/schema.yaml`
- canonical：`quwoquan_service/services/product-ops-service/config/schema.yaml`
- canonical：`quwoquan_ops/environments`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 配置 Provider 分层

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“配置 Provider 分层”对应的公开行为。
- THEN 统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod/`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-004"></a>
### GWT-004 四环境配置与拓扑无漂移

- GIVEN 从受控配置真相源生成任一环境的部署快照。
- WHEN 删除可重建输出后重新生成 alpha、beta、gamma 与 prod 快照。
- THEN 每个环境的配置、deploymentRef 与 workload topology 一致，且不产生第五环境或 prod-gray。

## 6. 依赖

- 前置要求：[`runtime-config`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 配置 Provider 分层 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“配置 Provider 分层”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
<a id="open-003"></a>
<a id="open-004"></a>
### OPEN-004 四环境配置与拓扑无漂移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：删除输出目录后仍可从受控真相源重建快照。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

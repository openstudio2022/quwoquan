# L3 Story：判定语义只来自显式声明 (`explicit-semantics-no-implicit-inference`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为所有 Scenario 提供「生效语义可追溯到一处声明」的装配与配置基线
>
> 设计归属：[L2 DEC-029](../design.md#dec-029)

## 1. 用户价值

作为在四个环境上部署同一份代码的开发者与运维者，我希望每一处行为分支都读得出「谁在哪个文件里声明了它」，从而在注入错了、漏了或与声明矛盾时立刻在装配期得到一条指名文件与键的判否，而不是让服务带着一份没人声明过的语义安静地跑起来。

## 2. 范围与非目标

### In Scope

- 判定语义的来源约束：分支只读显式声明，不读值的在场与形态。
- 「不启用 / 不接真实依赖」作为取值的合法枚举值，而非取值缺席。
- 配置取值的四层声明位与优先级，以及跨服务默认的边界。
- 一段配置的复用规则：整段缺席即复用，禁止字段级回落。
- URI scheme 作为协议契约的一部分被读取（豁免形态）。
- 判否的时机（装配期）、传播（error 不得被丢弃）与文本要求。

### Out of Scope

- 禁止默认值本身；有声明位的默认值是合法声明。
- 结果状态的表达形态（缺席/空/失败），归 [`absent-empty-failure-nullability`](../absent-empty-failure-nullability/spec.md) 与 [DEC-025](../design.md#dec-025)。
- Redis scene 地址注入成套性由 `test_redis_scene_address_provenance` 判定，归 [DEC-028](../design.md#dec-028)；本能力只拥有判否语义本身。
- 云上 prod 集群种子的注入归属，归本能力 [OPEN-014](../spec.md#open-014)。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分支只读显式声明

- 决定行为分支的语义必须来自显式声明位；不得以「某个值在不在场」或「某个值是/不是某种形状」作为判据。
- 「本环境不接真实依赖」必须是取值的一个合法枚举值。Redis 以 `mode: memory` 表达，ES 以 `SEARCH_ES_ENABLED` 表达。
- 一个能力的启用状态不得由另一个字段的在场翻转：注入端点不改变启用声明，注入地址不改变拓扑声明。
- 声明与注入互相矛盾时判否，不得挑一处生效：挑地址会让声明的关停失效，挑关停会让注入的地址静默失效。
- CLI 与工具入口把「本工具必需某依赖」写成无条件赋值是显式声明，不属于推断；判据是该赋值不读任何在场与形态。

<a id="req-002"></a>
### REQ-002 配置取值分四层，每层都是显式声明

- 取值优先级自高到低为：服务 `environments/<env>/config.yaml` override、环境级跨服务默认、全局跨服务默认、服务 `config/schema.yaml` 的 `default`。
- 任一生效值都能指回一处写下它的文件；渲染器对每个键记录取值来源。
- 跨服务默认只提供取值，不定义键：pattern 未命中本服务 schema 声明的键时该键不进入快照。键的存在性、类型与 `sensitive` 仍只由本服务 schema 声明。
- 跨服务默认的取值必须过本服务 schema 的类型校验，类型不符时判否且判否文本指名 defaults 文件。
- `sensitive` 键不得由跨服务默认提供，只能走 secretRef；跨服务默认命中 `sensitive` 键即判否。
- 跨服务默认按键 pattern 匹配，更具体的声明优先于更宽的 pattern；同一层内两条同等具体的 pattern 命中同一键即判否。

<a id="req-003"></a>
### REQ-003 整段缺席即复用，禁止字段级回落

- 一段配置只允许「整段缺席时复用另一段」这一条复用规则，判定为该段每个字段都未被声明过。
- 复用后的整段仍要过原有校验，复用不豁免校验。
- 禁止字段级回落：不得把一段的某个字段缺失时单独取另一段的同名字段。
- 复用规则写在装配处且只有一条，读者能从装配代码看出该段每个字段的来源。

<a id="req-004"></a>
### REQ-004 判否止于装配，且文本指名声明位

- 判否发生在装配期，不得降级为 no-op 实现、空 provider 或静默降级。
- 校验函数的返回值不得被调用方丢弃；吞掉 error 使装配期判否退化为注释里的承诺。
- 判否文本描述缺失的那处声明或注入键，并给出合法出路（含关停路径），不描述症状。
- URI scheme 是协议契约的一部分，读它是解析声明；OTLP endpoint 缺 scheme 判否，注入面必须写出 scheme。

## 4. 契约引用

- canonical：`quwoquan_service/services/*/config/schema.yaml`、`quwoquan_service/control-plane/*/config/schema.yaml`
- canonical：`quwoquan_ops/environments/config-defaults.yaml`
- 渲染器：`quwoquan_ops/cli/render_runtime_config.py`
- 装配面：`quwoquan_service/runtime/servicekit/redis.go`、`quwoquan_service/runtime/redis/router.go`、`quwoquan_service/internal/platform/redis/client.go`、`quwoquan_service/runtime/otel/otel.go`
- 设计决定：[L2 DEC-029](../design.md#dec-029)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 声明缺失与声明矛盾都在装配期判否

- GIVEN 一段 Redis scene 配置未声明 `mode`，或声明 `memory` 的同时被注入了地址。
- WHEN 装配该 scene。
- THEN 未声明 `mode` 时装配判否，不落回进程内存实现。
- AND 判否文本列出 `memory`/`standalone`/`cluster` 三个合法取值与可写入它们的声明位。
- AND 声明 `memory` 同时被注入地址时装配判否，不挑其中一处生效。
- AND 声明了不支持的 `mode` 取值时装配判否。

<a id="gwt-002"></a>
### GWT-002 声明的拓扑缺地址时判否而不降档

- GIVEN 一段 scene 声明 `standalone` 但未注入 `addr`，或声明 `cluster` 但只注入了单点 `addr`。
- WHEN 装配该 scene。
- THEN 两种形态都判否，不降档为进程内存实现也不把单点地址当成集群种子。
- AND 判否文本同时给出「注入缺的地址」与「改声明」两条出路。

<a id="gwt-003"></a>
### GWT-003 四层取值各自生效且来源可指回

- GIVEN 同一个键分别只在服务环境 override、环境级跨服务默认、全局跨服务默认、schema `default` 声明。
- WHEN 渲染该服务该环境的运行时配置快照。
- THEN 生效值取自优先级最高的那一层。
- AND 跨服务默认的 pattern 未命中本服务 schema 声明的键时该键不进入快照。
- AND 跨服务默认命中 `sensitive` 键时渲染判否。

<a id="gwt-004"></a>
### GWT-004 整段缺席复用，部分声明不触发复用

- GIVEN 一个服务的某个 scene 整段未声明，另一次只声明了它的一个字段。
- WHEN 解析该服务的 scene 集合。
- THEN 整段缺席时该段完整复用被指定的另一段声明。
- AND 只声明了一个字段时不发生复用，该段按自身声明校验并在声明不成套时判否。

<a id="gwt-005"></a>
### GWT-005 传输加密由 scheme 声明，缺声明判否

- GIVEN OTLP endpoint 分别取 `http://host:4318`、`https://host:4318` 与 `host:4318`。
- WHEN 构造 trace exporter。
- THEN 前两者分别按明文与加密传输。
- AND 缺 scheme 的第三者判否并要求写出 scheme。
- AND 该判否使装配失败，不产生「无 trace 但进程正常」的形态。

<a id="gwt-006"></a>
### GWT-006 新增一处在场性分支时门禁变红

- GIVEN 一段新代码读某个声明位（config struct 字段、schema 键或 env 键）是否在场，并据此进入不同分支。
- WHEN 运行显式语义门禁。
- THEN 门禁判否并指出该分支的位置与它读的那个声明位。
- AND 已合规的四处装配面（Redis mode、ES `Enabled`、scene 整段复用、OTLP scheme）不产生误报。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的 `REQ-002`、`REQ-003`。
- 上游事实：服务 config schema 的键定义与 `sensitive` 声明、四环境注入面。
- 下游结果：运行时配置快照的生效值与来源、装配期判否结论。
- 父级设计：`DEC-029`；Redis scene 的模式裁决见 `DEC-028`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 显式语义没有静态门禁，判据仍靠人工评审

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `REQ-001` 的判据（分支是否读了值的在场或形态）没有任何静态检查，只有本节 GWT 锁定的四处具体装配面——Redis mode、ES `Enabled`、scene 字段级复用、OTLP scheme。这四处不会重现，同类形态却可以在任何新代码、新服务里第一次出现而不被拦。这类推断的共同外观是「读一个字段是否为空、是否有某前缀，然后决定另一件事」，与大量合法的空值判断在语法上同形，因此门禁不能用「出现 `== \"\"`」这类判据，否则会产出压倒性误报并很快被绕过。缺的是可判定的收窄判据：先确定一份「声明位」清单（config struct 字段、schema 键、env 键），再只对「读声明位的在场性后进入不同分支」的形态下断言。
- 完成判定：`GWT-006` 的两条结果子句（`gwt-006.t1`、`gwt-006.t2`）具备门禁自证 `local_contract` 的子句级绑定证据——门禁对新增在场性分支变红，且对已合规的四处装配面不误报。

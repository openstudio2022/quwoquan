# L3 Story：领域引导验收治理 (`domain-onboarding-acceptance-governance`)

> 所属能力：[`runtime-control-plane-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望由物理路径、唯一拓扑与运行证据计算领域接入状态，禁止 onboarding/readiness 注册表，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- metadata/source/test 路径反向映射
- App、runtime、Ops 与领域服务的生产/测试/生成物/环境输出边界反向映射
- 四环境拓扑、配置和三层证据闭环
- 禁止第二真相源回潮

### Out of Scope

- 新建领域接入登记平台
- 旧 schema 或注册表兼容期

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 无登记领域接入治理

- 不存在第二真相源，且统一门禁能够发现路径、拓扑、配置、部署输出和证据漂移。
- 服务业务测试只能位于 canonical `tests/<layer>/<context>/<object>/`；production `internal/**` 与 `cmd/**` 的测试、production App 的 fixture/Mock 可达图、仓内或 `.qwq_output` 内的部署工作目录均为阻断项。

<a id="req-002"></a>
### REQ-002 没有 gamma/prod 当前证据时，派生状态必须保持未就绪，不得人工改成 ready

- 没有 gamma/prod 当前证据时，派生状态必须保持未就绪，不得人工改成 ready。

## 4. 契约引用

- canonical：`quwoquan_ops/gate/verify_service_architecture.py`
- canonical：`quwoquan_ops/environments`
- canonical：`object.yaml.kind`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 无登记领域接入治理

- GIVEN 领域对象、源码、部署和测试资产已进入统一扫描范围。
- WHEN 执行统一服务架构门禁并汇总三层测试结果。
- THEN domain/context/object/layer 可唯一反推，接入与 readiness 由证据计算。
- THEN 服务、App、runtime 与 Ops 的 production/test/generated/environment-output 路径均可由 metadata、依赖和环境契约反推，出现旧测试根、fixture/Mock production reachability、第二 composition root 或仓内 deploy work root 即阻断。
- THEN onboarding/readiness/对象服务注册表缺失不会阻断，出现则门禁失败。

## 6. 依赖

- 前置要求：[`runtime-control-plane-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 无登记领域接入治理

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：不存在第二真相源，且统一门禁能够发现路径、拓扑、配置和证据漂移。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

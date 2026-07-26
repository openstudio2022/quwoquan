# L3 Story：模板引擎与元数据读取器 (`template-engine-and-metadata-reader`)

> 所属能力：[`runtime-codegen`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望所有 generator 从统一 ContractGraph Source 取得契约并显式选择产物模板，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 统一 ContractGraph Source、模板到产物类型的显式注册，以及生成失败诊断。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 模板引擎与元数据读取器

- generator 必须从统一 ContractGraph Source 取得已校验契约，并通过显式注册选择模板与产物类型。
- 模板不得自行读取 YAML；契约加载或模板渲染失败时不得写入部分成功产物。

<a id="req-002"></a>
### REQ-002 Template Registration：模板名与产物类型显式映射；模板不能自行读取 YAML

- 模板名与产物类型必须显式映射；模板不能自行读取 YAML。
- 所有 generator 共用同一个 ContractGraph Source，禁止新增第二个 metadata parser。
- 模板渲染失败必须返回包含模板名、行号的错误。
- generate/check 必须幂等，missing、stale、orphan 任一失败。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 模板引擎与元数据读取器

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“模板引擎与元数据读取器”对应的公开行为。
- THEN generator 只从统一 Source 读取已校验契约，模板名与产物类型映射明确，重复执行结果一致。
- AND 契约加载或模板渲染失败时返回包含 generator、模板和定位信息的错误，且不产生部分成功产物。

## 6. 依赖

- 前置要求：[`runtime-codegen`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 模板引擎与元数据读取器 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“模板引擎与元数据读取器”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

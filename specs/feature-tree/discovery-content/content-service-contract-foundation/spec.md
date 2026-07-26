# L2 Business Capability：内容服务契约基础 (`content-service-contract-foundation`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“content-service-contract-foundation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`fullstack-error-behavior-contract`](./fullstack-error-behavior-contract/spec.md)：以服务本地 errors 和 behaviors 契约生成端云错误、恢复动作与行为信号。
- [`metadata-domain-restructure`](./metadata-domain-restructure/spec.md)：把业务域契约归入所属服务 contracts，仅保留跨服务共享 schema 在中心 metadata。
- [`privacy-ui-config-contract`](./privacy-ui-config-contract/spec.md)：由服务本地 privacy 与 ui_config 契约生成端云策略，未知或缺失策略默认拒绝。
- [`three-layer-test-contract`](./three-layer-test-contract/spec.md)：定义“三层分层测试契约”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 内容服务契约基础能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 端侧 UI 禁止直接 import 横切常量之外的任何 metadata 文件

- 端侧 UI 禁止直接 import 横切常量之外的任何 metadata 文件

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`MODULE.KIND.REASON`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 content service contract foundation 能力 SIT

- GIVEN 执行“content service contract foundation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“content service contract foundation 能力”对应动作。
- THEN 直属 Story 共同交付“内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录”，失败终态可区分且不产生伪成功事实。

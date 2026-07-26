# L2 Design：内容服务契约基础 (`content-service-contract-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调”需要 `fullstack-error-behavior-contract`、`metadata-domain-restructure`、`privacy-ui-config-contract`、`three-layer-test-contract` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`fullstack-error-behavior-contract`](./fullstack-error-behavior-contract/spec.md)：以服务本地 errors 和 behaviors 契约生成端云错误、恢复动作与行为信号。
- [`metadata-domain-restructure`](./metadata-domain-restructure/spec.md)：把业务域契约归入所属服务 contracts，仅保留跨服务共享 schema 在中心 metadata。
- [`privacy-ui-config-contract`](./privacy-ui-config-contract/spec.md)：由服务本地 privacy 与 ui_config 契约生成端云策略，未知或缺失策略默认拒绝。
- [`three-layer-test-contract`](./three-layer-test-contract/spec.md)：定义“三层分层测试契约”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`MODULE.KIND.REASON`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 服务本地 contracts 驱动端云生成、错误和三层测试
- 决策：服务本地 contracts 驱动端云生成、错误和三层测试。
- 理由：内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`fullstack-error-behavior-contract`](./fullstack-error-behavior-contract/spec.md)、[`metadata-domain-restructure`](./metadata-domain-restructure/spec.md)、[`privacy-ui-config-contract`](./privacy-ui-config-contract/spec.md)、[`three-layer-test-contract`](./three-layer-test-contract/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 端侧 tab 配置硬编码在 UI 代码。
- 方案 C：外部配置中心（Remote Config）
- feature flags 和 tab 顺序放远程配置服务（Firebase/自建）

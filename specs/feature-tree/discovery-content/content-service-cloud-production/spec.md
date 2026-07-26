# L2 Business Capability：内容服务云端交付 (`content-service-cloud-production`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让经数据生产和审核的文章、图片、视频及主页内容以不可变发布物进入 content-service，并由 App 通过正式远端契约读取。

## 2. 范围与非目标

### In Scope

- homepage/article/image/video 的五阶段执行产物与 immutable execution identity。
- release create-once、环境执行、导入校验和 App 远端读取。
- canonical objects、引用闭包与发布证据。

### Out of Scope

- 内容生产 prompt 和草稿的产品策略；由 data engineering 负责。
- App 页面布局和推荐排序；由对应 discovery 能力负责。

## 3. Journey / Scenario 贡献

- 当前由父 L1 将本能力组合进发现、浏览和创作 Journey；本能力负责“正式内容可被远端读取”的交付段。

## 4. Story



- [`remote-content-delivery`](./remote-content-delivery/spec.md)：缺 release、路径逃逸或悬挂引用必须拒绝导入；成功导入后 App 必须通过统一 gateway 读取，不得回退 fixture。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 不可变内容发布与导入

- 四种 contentType 共用五阶段 required-artifact 契约，并对 Schema 和悬挂引用 fail-closed。
- execution identity 对不可变核心确定；resume 只能追加 checkpoint 和 log。
- release 同 ID 只能创建一次，且不得包含 prompt、draft、repair 或原始日志。
- importer 必须同时消费 canonical objects 与 immutable release desired state。

<a id="req-002"></a>
### REQ-002 端云单轨交付

- 服务对象、operation、event 和 error 必须来自 content-service metadata/codegen。
- App Remote 必须通过运行时配置和生成契约调用真实服务，不得以 Mock 结果作为集成证据。
- 环境执行只读 desired state，并将证据 append-only 写入对应 env run。

## 6. 契约与依赖

- 上游能力：数据生产和内容审核公开的 release/canonical objects。
- 下游能力：内容浏览、主页聚合、搜索和推荐读取面。
- 读取事实：immutable release、canonical content objects。
- 写入事实：content-service 拥有的内容聚合与导入证据。
- operation/event/object：引用 `quwoquan_service/services/content-service/contracts/`。
- 一致性要求：release create-once；服务导入和 App 读取不得接受旧 wire 键。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 正式内容从发布物进入 App

- GIVEN 一个通过 Schema、引用闭包和审核校验的不可变内容 release。
- WHEN content-service importer 执行导入且 App 通过 Remote operation 读取对应内容。
- THEN 服务只写入 canonical objects，App 得到 metadata 定义的正式响应。
- AND 缺 release、路径逃逸、悬挂引用或 Mock-only 数据都会被拒绝且不伪造成功。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 真实环境端到端发布证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：需要持续证明 release、真实 importer、服务存储和 App Remote 在目标环境中闭环。
- 完成判定：`SIT-001` 在匹配环境中具有有效 `api_integration` 与 `user_acceptance` 的 `spec_ref`。

# runtime 设计

## 设计动因

业务域需要共享错误、配置、HTTP、消息、可观测、治理、平台防腐与外部 Provider 机制，
但不能因此把业务对象、部署进程和第三方 SDK 混成一个“平台层”。runtime 的职责是提供
稳定机制合同、构建期验证和显式装配。

## 边界

- `quwoquan_service/runtime/**` 提供跨服务机制接口与实现；不拥有业务 aggregate。
- `quwoquan_app/lib/cloud/runtime/**` 与 `lib/core/platform/**` 提供客户端 transport、
  RuntimeFailure 和平台防腐；UI 只消费 capability。
- `integration-service` 是 runtime 治理的独立机制进程，按 metadata 业务对象提供 typed
  Facade；它不是 `integration` L1，也不是所有外部依赖的万能代理。
- `quwoquan_ops` 提供环境 Binding、显式 composition、readiness、证据和发布门禁。

## 依赖与装配

```text
domain <- application <- adapters <- infrastructure
```

对象和能力合同来自 metadata/ContractGraph；具体 Store、Reader、Provider Adapter 在各
composition root 显式选择。compiler 可以在构建期交叉校验 metadata、registry、环境
Binding、依赖和 acceptance，服务启动不得扫描仓库 metadata 或按字符串反射选实现。

## 独立部署机制

独立进程必须满足：

- 服务边界由 runtime L2 能力拥有，部署名不形成第二棵领域树；
- 对外只暴露 generated operation/typed Facade；
- required 依赖缺失时 fail-closed，readiness 可按能力解释；
- 配置、错误、观测、灰度与回滚复用 runtime/Ops 单轨机制；
- App、Service、Data 业务代码不能直接依赖该进程所封装的 Vendor SDK/DTO。

## 测试与发布

L1 以 domain acceptance 证明边界和工程映射；L2 以 SIT 验证能力组合；L3 以 GWT/contract
验证状态机和异常。物理测试层只有 local_contract、api_integration、user_acceptance；
环境和 rollout stage 是证据维度。任何商用外部能力缺 Gamma 真实 Adapter、观测或回滚
证据时必须保持 blocked。

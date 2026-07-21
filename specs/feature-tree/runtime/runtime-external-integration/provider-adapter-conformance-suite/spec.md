# L3 Story：provider-adapter-conformance-suite

## 用户价值

同一外部能力无论选择哪家 Provider，都必须表现出一致的业务成功、失败、恢复、隐私和
观测语义；上线结论来自真实执行证据，而不是 Adapter 名称、测试文件存在或人工勾选。

## 范围

- 定义 Provider 公共场景：success、validation、authentication、DNS/network、timeout、
  throttle、retry、idempotency、duplicate/out-of-order callback、redaction、observability。
- 允许能力专项 profile 追加协议场景，但不得删减公共场景。
- Go、Dart、Python 使用各自原生 harness；共享 scenario ID、fault model 和 evidence schema。
- 生成 Alpha/Beta/Gamma × local_contract/api_integration/user_acceptance 九格报告。
- 拒绝 NOT_RUN、required skip、零断言、dry-run、旧 digest、缺观测和泄密证据。

## 约束

- `local_contract` 永不访问外网；Beta/Gamma 只是在离线 harness 中加载对应 production
  Adapter 类和绑定 profile。
- `api_integration` 必须连接该环境声明的真实 Provider/兼容服务，不得改跑内存实现。
- `user_acceptance` 必须验证用户或运营结果、失败提示、恢复与可查询观测。
- evidence 仅记录 `endpointRef/secretRef/configDigest`，不得记录实际 endpoint、环境变量、
  credential、token、PII 或完整渲染配置。
- 报告只写入 `.qwq_output` 的 runs/observability 分类；manifest、schema 和命令映射留在
  `quwoquan_ops/environments/**`。

## 完成条件

- 每个登记 Adapter 都解析出公共 profile 和能力专项 profile。
- 九格聚合只接受同一 commit、image、config、ContractGraph 和 Adapter digest。
- 任一 required cell 缺失或失败时 Adapter/Capability readiness 保持 false。
- suite 自身具备正负例 local_contract，能够证明假 report、skip、零断言、旧 digest、
  泄密和 output 目录越界均被阻断。

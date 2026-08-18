# architect · dev · app-wiring

适用：改动触及 `quwoquan_app/lib/**` 的装配、页面数据依赖或平台能力。
真相源：[production-wiring-and-test-doubles](../../references/production-wiring-and-test-doubles.md)、
[app-layering](../../references/app-layering.md)、[page-ownership](../../references/page-ownership.md)。

## DURING 执行中

- [MUST NOT] 页面与 Provider 依赖聚合 Repository，或依赖 `AppDataSourceMode` 等运行时数据源切换
  gate: make verify-app-mock-isolation
- [MUST NOT] Remote adapter 失败后返回 fixture、空集合、Mock 结果、本地合成成功，
  或吞掉 `RuntimeFailure`
  gate: make verify-app-mock-isolation
- [MUST NOT] 在 `lib/**` 新增 `Mock*` / `Stub*` / `Noop*` 或测试专用 factory
  gate: make verify-app-mock-isolation
- [MUST NOT] 业务层裸用 `MethodChannel` / `EventChannel`；原生能力经
  `lib/runtime/platform/**` 的 `NativeBridge` 抽象
  gate: make verify-app-page-horizontal-quality

## POST 自检

- [MUST] Mock 隔离通过
  gate: make verify-app-mock-isolation
- [MUST] 云包边界通过
  gate: make verify-app-cloud-package-boundaries
- [MUST] 生产数据源单路径通过
  gate: make verify-app-production-data-source-single-path
- [MUST] 生产装配纯度通过（对象扩展或装配改动时）
  gate: make verify-production-wiring-purity
- [MUST] 契约图与其输入一致（对象扩展时）
  gate: make verify-app-contract-handoff-inputs

## HANDOFF 交接

- 产出：装配与页面数据依赖的改动点
- 未决项去向：临时装配妥协转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出

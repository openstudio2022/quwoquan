# test/support/runtime — 横切测试基础设施

与 [`app-cloud-business-object-commercial-closure`](../../../../specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004) 对齐。

## 规则

- **仅** `test/**` 应引用 `test/support/**`；**禁止** `lib/**` import 测试支持代码。
- 业务 typed double、fixture factory 与对象 runner helper 必须放在
  `test/support/<domain>/<context>/<object>/`，不得汇总到共享 barrel。
- 本目录只保存 Cloud 边界、transport、platform、shell、codec 等横切 harness；
  不得保存业务 Repository、对象 fixture 或环境形状的数据替身。
- 本地契约按生产对象放在 `test/local_contract/<domain>/<context>/<object>/`；跨对象 typed-double/Provider/Widget Journey 只放 `test/local_contract/journeys/<journey>/`，不得回到 legacy `cloud/ui/core` 根。
- `api_integration` 必须通过 generated client 与 production Remote adapter 访问真实进程；raw HTTP helper、内存实现或 fake server 只能作为 local-contract/support 证据，不能冒充 API integration 通过。
- 端侧环境测试统一放在 `test/local_contract`、`test/api_integration`、`test/user_acceptance`；设备/模拟器由对应 runner 参数决定。

# Environment Test Layout Contract

环境不参与测试目录分层。测试对象按三层目录组织，环境只进入 runner 参数、`.qwq_output/env/<env>/runs/**` 报告和 recorded artifact。

## App

```text
quwoquan_app/test/
  local_contract/{ui,cloud,core,app,quality}/
  api_integration/{ui,cloud,observability,security,performance}/
  user_acceptance/{journeys,pages,patrol,quality}/
  support/
```

禁止出现 App 旧测试根：`ui`、`cloud`、`components`、`core`、`app`、`common`、`beta`、`gamma`、`patrol`、`smoke`。这些名称只能作为 canonical 根下的测试对象子目录存在。

## Service

```text
quwoquan_service/services/<service>/tests/
  local_contract/
  api_integration/
  support/
```

服务包内白盒 Go 测试必须使用 `__local_contract_test.go` 后缀。跨环境 smoke/gate/CI 归 `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/<service>/`。

## Data

```text
quwoquan_data/tests/{local_contract,api_integration,user_acceptance,support}/
```

## Ops

```text
quwoquan_ops/tests/
  local_contract/
  acceptance/{api_integration,user_acceptance}/
  support/
```

## Environment Runner

- `ENV=beta|gamma|prod make test-api-integration`
- `TARGET=local|gamma-local|prod-hosted make test-user-acceptance`
- 运行报告只写 `.qwq_output/env/<env>/runs/**` 或 `.qwq_output/env/repo/runs/tests/**`
- 测试 fixture 来自 `contracts/metadata/**/test_fixtures` 或 `test/support/**`，不通过环境目录复制。

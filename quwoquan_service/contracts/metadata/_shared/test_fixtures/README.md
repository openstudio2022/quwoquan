# Contract Scenario Fixtures

`test_fixtures` 只保存 `local_contract` 与 `api_integration` 测试树使用的对象级 typed double 资产。它不参与环境 package、runtime bootstrap 或 user_acceptance 数据供给。

## 目录约定

```text
contracts/metadata/{domain}/test_fixtures/scenarios/{domain}_scenarios.json
```

## 环境约定

- `local_contract` / `api_integration`：测试树内对象级 typed double 可读取测试资产。
- `alpha` / `beta` / `gamma`：内容由 canonical immutable release 激活；账号、评论、圈子、会话和消息由 `stackctl verify` 使用真实非生产主体调用公开 command/event 创建。
- `prod`：不包含或读取本目录，也不执行任何 nonprod provision runner。

## 字段约定

- `seedSets`：仅用于测试进程内 typed double 初始化。
- `scenarios`：测试入口，只引用 `seedRefs` 与断言期望。
- `repositoryExpectations`：测试 double 的对象级契约。
- `remoteExpectations`：API integration 的契约断言，不是环境 seed。
- `uiExpectations`：页面层可见文案、首屏关键元素等断言。

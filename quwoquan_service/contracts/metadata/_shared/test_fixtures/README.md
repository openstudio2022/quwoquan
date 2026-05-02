# Contract Scenario Fixtures

`test_fixtures` 是端云 alpha/beta/gamma 测试数据的契约资源区。该目录不参与实体 registry 聚合，供 Dart/Go 测试 loader 与本地 beta seed runner 读取。

## 目录约定

```text
contracts/metadata/{domain}/test_fixtures/scenarios/{domain}_scenarios.json
```

跨域共享规范位于：

```text
contracts/metadata/_shared/test_fixtures/scenario_fixture.schema.json
```

## 环境约定

- `alpha`：端侧通过 MockRepository 读取 fixture seed。
- `beta`：端侧通过 RemoteRepository 访问本地云服务；云服务测试前 reset + seed。
- `gamma`：复用同一 fixture artifact，只替换网关、认证、部署与观测配置。
- `prod-gray` / `prod`：不读取测试 fixture。

## 字段约定

- `seedSets`：云侧或端侧 mock 初始化数据。
- `scenarios`：测试入口，只引用 `seedRefs` 与断言期望。
- `repositoryExpectations`：环境到数据源的唯一契约。
- `remoteExpectations`：beta/gamma 远端返回断言。
- `uiExpectations`：页面层可见文案、首屏关键元素等断言。

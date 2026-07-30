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

- `local_contract`：测试树内对象级 typed double 可读取 fixture seed；Alpha 与其他环境 App 不得消费本目录。
- `beta`：端侧通过 RemoteRepository 访问本地云服务；云服务测试前 reset + seed。
- `gamma`：`app_gamma_seed_manifest.json` 是 curated 场景选择的唯一真相源；其中以 `*.gamma-curated.json` 结尾的条目必须声明 `curation`，并由 `make verify-gamma-curated-scenarios` 校验派生结果。更新选择后只执行 `make generate-gamma-curated-scenarios`，禁止手改派生 JSON。
- Gamma runtime 业务数据与媒体只由 canonical immutable release activation 交付；测试场景投影器不写 manifest、不生成媒体 bundle，也不承担环境 seed。
- `prod`：不读取测试 fixture。

## 字段约定

- `seedSets`：云侧或端侧 mock 初始化数据。
- `scenarios`：测试入口，只引用 `seedRefs` 与断言期望。
- `repositoryExpectations`：环境到数据源的唯一契约。
- `remoteExpectations`：beta/gamma 远端返回断言。
- `uiExpectations`：页面层可见文案、首屏关键元素等断言。

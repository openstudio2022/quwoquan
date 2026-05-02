# test/support — 共享夹具根目录

与 [`specs/gates/mock_data_cloud_integration_policy.md`](../../../specs/gates/mock_data_cloud_integration_policy.md) **§9.2** 对齐。

## 子目录

| 目录 | 用途 |
|------|------|
| `fakes/` | 跨用例 `FakeHttpClient`、Fake Repository、`ProviderScope` 覆盖桩等 |
| `fixtures/` | JSON / 二进制 / 大段样例（可按域分子目录，如 `chat/`） |
| `harness/` | `pumpApp`、测试用路由桩、统一 `ProviderContainer` 构建 |

## 规则

- **仅** `test/**` 应引用本目录；**禁止** `lib/**` import `test/support/**`。
- 契约测试仍优先放在 `test/cloud/{domain}/contract/`；数据源用 `Mock*Repository` 或本目录 **fakes**，勿从 `lib/.../mock/` 再复制一份业务 Map。
- 端侧环境测试统一放在 `test/common|alpha|beta|gamma|patrol`；设备/模拟器由 runner 参数决定。

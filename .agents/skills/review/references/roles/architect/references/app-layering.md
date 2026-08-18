# App 分层与目录归属

`quwoquan_app/lib` 只有四个顶层去处：

```
lib/design_system/     跨服务复用的视觉与交互积木
lib/runtime/           与业务对象无关的运行时底座
lib/service/           业务，按 <service>_service/<context>/<object> 组织
lib/l10n/              生成的本地化
```

判断新文件去哪：**它是否绑定某个业务对象**。绑定则进 `lib/service`，
不绑定但属运行时能力进 `lib/runtime`，不绑定且是可复用 UI 积木进 `lib/design_system`。

## 业务对象四层

`lib/service/<service>_service/<context>/<object>/` 下固定四层，职责不可越界：

| 层 | 只放 | 禁止 |
|---|---|---|
| `domain` | 领域类型与规则 | 依赖 Flutter、网络、存储 |
| `application` | 对象级 `*CommandWriter` / `*Query` port 与少量 coordinator | 聚合 Repository、动态 wire |
| `adapters` | generated client 到 application port 的薄映射 | 由调用方传入 URL、operationId、auth、decoder、retry、deadline、error policy |
| `presentation` | 页面与 Provider | 直接依赖 `adapters` 或聚合 Repository |

- [MUST NOT] 页面与 Provider 依赖聚合 Repository 或运行时数据源开关；
  只依赖对象级 typed port，理由见
  [production-wiring-and-test-doubles.md](production-wiring-and-test-doubles.md)。
- [MUST NOT] 一个 UI 模块直接 import 另一个 UI 模块的内部文件；
  共享经 `lib/design_system` 或对象级 public port。

## generated 契约

- [MUST] pure Dart 的 request / result / Slice / error / descriptor 只由 ContractGraph
  生成到 `packages/quwoquan_cloud_contracts`。
- [MUST NOT] 在 App 树内维护业务契约副本，也不手改任何 `.g.dart`。

## lib/runtime

只保留与业务对象无关的底座：`auth`、`cache`、`codec`、`config`、`context`、`di`、
`errors`、`models`、`observability`、`platform`、`services`、`shell`、`transport`、`testing`。

- [MUST NOT] `lib/runtime` 依赖 UI、Router、Provider、fixture、local store 或平台插件。
  平台能力经 `lib/runtime/platform` 的防腐层，见
  [capability-portability.md](capability-portability.md)。
- production composition 在 `lib/runtime/di/`，四环境统一只装配 Remote；
  对象级 typed double 只能存在于 `test/local_contract` 树，runner 与 UAT support 不得注入。

## 规格同步

行为发生变化时，同 PR 更新对应 `spec.md` 的 REQ/GWT/SIT/UAT，
并让测试的 `spec_ref` 指向稳定锚点。

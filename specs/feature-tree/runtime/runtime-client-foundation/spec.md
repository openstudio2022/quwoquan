# L2 特性：runtime-client-foundation

## 功能说明

端侧 App（Flutter）的**平台级基础设施层**，与服务端 `runtime-*` 系列平行，覆盖所有跨功能域的客户端运行时能力。当前包含两个子模块：

| L3 子模块 | 职责 |
|---|---|
| `app-locale-infrastructure` | 国际化（i18n）基础设施：ARB 文件 + `flutter gen-l10n` 代码生成 + 字符串常量迁移 |
| `app-theme-infrastructure` | 主题基础设施：dark/light 模式切换机制（待后续交付） |
| `error-permission-display-semantics` | 云端/网络错误与权限类统一展示语义：内联 vs SnackBar、权限卡片、token 约束（规范见 `specs/ux/error-and-permission-semantics.md`） |
| `page-layout-semantics` | 页面布局统一语义：Modal/Stack leading、选择器模式、设置页结构（规范见 `specs/ux/page-layout-semantics.md`；不含用户/作者/圈子主页） |
| `dart-semantic-gate` | Dart 编码规范自动化守门：verify_dart_semantic 脚本 + gate 集成 + 规则增强 + FF 前置 |
| `ios-native-page-enforcement` | iOS 原生页面根壳与静态门禁（Material 根 `Scaffold` 阻断） |
| `metadata-driven-client-data-contract` | 客户端 **消费侧** 与 `contracts/metadata` codegen 对齐：UI/Mock/Remote 同源类型与缺口清单 |

## 职责边界

- 负责：App 级别的跨域横切能力（locale、theme、未来可扩展 analytics 上报基础等）
- 不负责：具体功能页面的业务逻辑；各功能域内的 UI 布局与交互
- 不负责：Go 服务端 runtime（由 `runtime-*` 各 L2 负责）

## 与父/子节点关系

- 父节点：`runtime` L1（基础设施与运行时层）
- 子节点：`app-locale-infrastructure`（L3）、`app-theme-infrastructure`（L3，待建）、`error-permission-display-semantics`（L3）、`page-layout-semantics`（L3）、`dart-semantic-gate`（L3）、`ios-native-page-enforcement`（L3）、`metadata-driven-client-data-contract`（L3）

## 约束

- 所有客户端横切能力必须经此 L2 统一定义，禁止在业务域 L2（如 `discovery-content`）下新建客户端基础设施节点
- **元数据 YAML 的唯一编辑仍归属 `contracts/metadata` + codegen 主线**；本 L2 的 `metadata-driven-client-data-contract` 仅约束 **Flutter 侧类型消费与 Mock/Remote 同源**，不替代云侧 metadata 评审流程
- 纯客户端 Gate（如 iOS 壳、dart semantic）不涉及 Go codegen；**可选** 元数据驱动 UI 门禁见该 L3 的 `plan.yaml`

## 验收标准概要

- A1：`app-locale-infrastructure` 交付后，`lib/ui/` 目录内无硬编码 CJK 字符串字面量
- A7：ARB 文件与 `UITextConstants`/`AppStrings` 常量覆盖一致（无遗漏 key）
- A8：`flutter analyze` + `flutter gen-l10n` 零报错

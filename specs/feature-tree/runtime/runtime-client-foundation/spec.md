# L2 特性：runtime-client-foundation

## 功能说明

端侧 App（Flutter）的**平台级基础设施层**，与服务端 `runtime-*` 系列平行，覆盖所有跨功能域的客户端运行时能力。当前包含若干子模块：

| L3 子模块 | 职责 |
|---|---|
| `app-locale-infrastructure` | 国际化（i18n）基础设施：ARB 文件 + `flutter gen-l10n` 代码生成 + 字符串常量迁移 |
| `app-theme-infrastructure` | 主题基础设施：dark/light 模式切换机制（待后续交付） |
| `cold-start-performance` | 冷启动 TTID、Welcome 首帧、路由/插件延后初始化与 startup ratchet 门禁 |
| `error-permission-display-semantics` | 云端/网络错误与权限类统一展示语义：内联 vs SnackBar、权限卡片、token 约束（规范见 `specs/ux/error-and-permission-semantics.md`） |
| `page-layout-semantics` | 页面布局统一语义：Modal/Stack leading、选择器模式、设置页结构（规范见 `specs/ux/page-layout-semantics.md`；不含用户/作者/圈子主页） |
| `dart-semantic-gate` | Dart 编码规范自动化守门：verify_dart_semantic 脚本 + gate 集成 + 规则增强 + FF 前置 |
| `ios-native-page-enforcement` | iOS 原生页面根壳与静态门禁（Material 根 `Scaffold` 阻断） |
| `metadata-driven-client-data-contract` | 客户端 **消费侧** 与 `contracts/metadata` codegen 对齐：UI/Mock/Remote 同源类型与缺口清单 |
| `article-editor-refactor` | 沉浸文章编辑器完全重构：WYSIWYG 卡片编辑、底栏五工具 + 撤销重做、排版/样式/序号/图与环绕等（规格见同目录 `article-editor-refactor/spec.md`） |
| `local-cache-architecture` | 客户端对象级缓存、查询快照、资源缓存、端云同步一致性与用户分层清理入口 |
| `app-remote-config` | App 远程运营配置：运营参数、feature flag、kill switch、LKG 快照与生效策略 |
| `public-content-web-entry` | 公开内容 Web 入口闭环：公开 HTML SEO 投影、站外 HTTPS 分享、PC 内容浏览与安装转化 |

## 职责边界

- 负责：App 级别的跨域横切能力（locale、theme、未来可扩展 analytics 上报基础等）
- 不负责：具体功能页面的业务逻辑；各功能域内的 UI 布局与交互
- 不负责：Go 服务端 runtime（由 `runtime-*` 各 L2 负责）

## 与父/子节点关系

- 父节点：`runtime` L1（基础设施与运行时层）
- 子节点：`app-locale-infrastructure`（L3）、`app-theme-infrastructure`（L3，待建）、`cold-start-performance`（L3）、`error-permission-display-semantics`（L3）、`page-layout-semantics`（L3）、`dart-semantic-gate`（L3）、`ios-native-page-enforcement`（L3）、`metadata-driven-client-data-contract`（L3）、`article-editor-refactor`（L3）、`local-cache-architecture`（L3）、`app-remote-config`（L3）、`public-content-web-entry`（L3）

## 约束

- 所有客户端横切能力必须经此 L2 统一定义，禁止在业务域 L2（如 `discovery-content`）下新建客户端基础设施节点
- **元数据 YAML 的唯一编辑仍归属 `contracts/metadata` + codegen 主线**；本 L2 的 `metadata-driven-client-data-contract` 仅约束 **Flutter 侧类型消费与 Mock/Remote 同源**，不替代云侧 metadata 评审流程
- 纯客户端 Gate（如 iOS 壳、dart semantic）不涉及 Go codegen；元数据驱动 UI 门禁见对应 L3 `spec.md` / `acceptance.yaml`
- 对象级缓存、查询快照、资源缓存和用户缓存清理统一归属 `local-cache-architecture`；业务域只登记对象策略与验收，不得自建第二套缓存合同或页面级 TTL。

## 验收标准概要

- A1：`app-locale-infrastructure` 交付后，`lib/ui/` 目录内无硬编码 CJK 字符串字面量
- A7：ARB 文件与 `UITextConstants`/`AppStrings` 常量覆盖一致（无遗漏 key）
- A8：`flutter analyze` + `flutter gen-l10n` 零报错

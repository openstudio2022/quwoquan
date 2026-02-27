# L2 特性：runtime-client-foundation

## 功能说明

端侧 App（Flutter）的**平台级基础设施层**，与服务端 `runtime-*` 系列平行，覆盖所有跨功能域的客户端运行时能力。当前包含两个子模块：

| L3 子模块 | 职责 |
|---|---|
| `app-locale-infrastructure` | 国际化（i18n）基础设施：ARB 文件 + `flutter gen-l10n` 代码生成 + 字符串常量迁移 |
| `app-theme-infrastructure` | 主题基础设施：dark/light 模式切换机制（待后续交付） |

## 职责边界

- 负责：App 级别的跨域横切能力（locale、theme、未来可扩展 analytics 上报基础等）
- 不负责：具体功能页面的业务逻辑；各功能域内的 UI 布局与交互
- 不负责：Go 服务端 runtime（由 `runtime-*` 各 L2 负责）

## 与父/子节点关系

- 父节点：`runtime` L1（基础设施与运行时层）
- 子节点：`app-locale-infrastructure`（L3）、`app-theme-infrastructure`（L3，待建）

## 约束

- 所有客户端横切能力必须经此 L2 统一定义，禁止在业务域 L2（如 `discovery-content`）下新建客户端基础设施节点
- 本 L2 变更不涉及 `contracts/metadata/` YAML，无 Go codegen，Gate 适配为纯客户端检查

## 验收标准概要

- A1：`app-locale-infrastructure` 交付后，`lib/ui/` 目录内无硬编码 CJK 字符串字面量
- A7：ARB 文件与 `UITextConstants`/`AppStrings` 常量覆盖一致（无遗漏 key）
- A8：`flutter analyze` + `flutter gen-l10n` 零报错

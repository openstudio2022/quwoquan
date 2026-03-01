# L3 子特性：error-permission-display-semantics

## 功能说明

端侧**云端/网络错误**与**权限类**的统一展示语义与交互契约，适用于所有涉及云端交互与系统权限的页面。与 `specs/ux/error-and-permission-semantics.md` 一一对应。

| L4 子节点 | 职责 |
|-----------|------|
| `cloud-network-error-display-contract` | 云端/网络错误的展示方式（内联 vs SnackBar）、语义 token、l10n 约定 |
| `permission-card-display-contract` | 权限卡片统一形态、权限类型与 l10n、去设置交互 |

## 范围

**云端/网络错误**：
- 页面加载、列表加载、编辑/提交失败的展示方式选择
- 阻塞性 → 内联占位；次要 → SnackBar
- 颜色、字号、间距等语义 token
- 通用 l10n key：loadFailed、submitFailed、networkUnavailable

**权限类**：
- 定位、相册、相机、麦克风等权限的卡片形态
- 永久拒绝时的「去设置」主操作
- 权限类型与 l10n key 映射

## 适用范围与约束

- **适用**：发现、创作、聊天、圈子、设置等所有涉及云端请求或系统权限的页面
- **不适用**：纯本地逻辑、无网络/权限依赖的页面
- **约束**：必须使用设计系统 token（AppTypography、AppSpacing、AppColors）；文案必须来自 l10n

## 与父/子节点关系

- 父节点：`runtime-client-foundation` L2
- 子节点：`cloud-network-error-display-contract` L4、`permission-card-display-contract` L4

## 与上下游关系

- **依赖**：`app-locale-infrastructure`（l10n 基础设施）、`fullstack-error-behavior-contract`（content 域错误码 codegen）
- **被依赖**：创作页、发现页、位置选择器、媒体选择器等

## 验收标准概要

- A1：云端阻塞性错误使用内联占位，次要错误使用 SnackBar
- A2：错误/权限展示均使用 AppTypography、AppSpacing、AppColors
- A3：权限永久拒绝时展示「去设置」主操作
- A4：07-error-permission-semantics 规则与特性树节点一致

## 测试目录约定（按领域服务划分）

- 统一按领域服务划分：禁止 `test/features/`、禁止 `test/cloud/integration/` 顶层
- 集成归属使用它的领域：content 使用 location → `test/cloud/content/location/`、`test/ui/content/entry/`
- 领域与实体使用名词：entry（创作入口）、location、post；禁止 create、publish 等动词
- 验证核心：**交互过程的异常**（权限拒绝、云端超时、加载失败）的 UI 表现；弱化纯 l10n key 存在性测试

# L3 子特性：error-permission-display-semantics

## 功能说明

端侧**云端/网络错误**、**权限类**、**登录门禁**与**提交/局部动作失败**的统一展示语义与交互契约，适用于所有涉及云端交互、系统权限与需要账号身份的页面。与 `specs/ux/error-and-permission-semantics.md` 一一对应。

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

**登录门禁与动作失败**：
- `AuthGateReason` + `AuthContinuation` 的统一用户语义
- 页面首屏 / 区块 / 列表追加 / 提交 / dialog 操作五类错误载体
- `UiErrorSemantic` 与统一 resolver 契约
- 有旧数据时的非阻塞错误展示
- 表单提交与字段校验分层：`UiErrorScope.form` 使用 `formInlineCard`，字段校验使用 `inlineField`
- 字段、表单、操作与服务状态的非阻断内联错误共用透明错误行：16px 圆形感叹号、14px 常规文字、6px 间距；错误前景/边框浅色为 `#E5484D`、深色为 `#FF6B6B`
- 错误标题、说明与操作的互斥语义，以及从错误态退出的唯一清晰路径
- 视频播放失败的内联覆盖层：可重试时只展示“再试一次”，不可重试时提供非按钮替代路径

**导航与错误容器边界**：
- 栈页面保留宿主导航栏返回，错误组件不再额外注入 X 或“返回” CTA
- 模态容器使用 X / barrier / 下滑关闭，不在内容错误态中复制退出控件
- 整页阻塞、区块阻塞、局部软失败、刷新失败、分页失败必须选择不同载体，不得用同一灰色卡片覆盖所有失败

## 适用范围与约束

- **适用**：发现、创作、聊天、圈子、设置、对象页、评论弹层等所有涉及云端请求、系统权限或登录门禁的页面
- **不适用**：纯本地逻辑、无网络/权限依赖的页面
- **约束**：必须使用设计系统 token（AppTypography、AppSpacing、AppColors）；文案必须来自 l10n
- **门禁**：页面不得直接消费裸 `RuntimeFailureKind` 或手写 “加载失败/请先登录/操作失败” 作为最终页态语义

## 与父/子节点关系

- 父节点：`runtime-client-foundation` L2
- 子节点：`cloud-network-error-display-contract` L4、`permission-card-display-contract` L4

## 与上下游关系

- **依赖**：`app-locale-infrastructure`（l10n 基础设施）、`fullstack-error-behavior-contract`（错误码 codegen）、`auth-gate-matrix`（登录门禁矩阵）
- **被依赖**：创作页、发现页、位置选择器、媒体选择器、评论弹层、群聊发起、对象页表单等

## 验收标准概要

- A1：云端阻塞性错误使用页态/区块态，次要动作失败使用轻量反馈
- A2：错误/权限/登录门禁展示均使用 AppTypography、AppSpacing、AppColors
- A3：权限永久拒绝时展示「去设置」主操作
- A4：登录门禁提示能表达“为何需要登录”与“登录后继续什么动作”
- A5：首屏失败、缓存回退失败、分页追加失败在列表页中有不同载体
- A6：07-error-permission-semantics 规则与特性树节点一致
- A7：沉浸式或跨页面入口的首屏错误必须保留来源 `sourceAppearanceMode`，错误页不继承错误的深色沉浸上下文
- A8：JIT 权限（按住说话、RTC）默认无 L2 App primer，同手势无 2+ App modal
- A9：聊天语音发送失败仅 status bar（`chatVoicePendingRetry`），禁止 actionDialog 叠加
- A10：L2 primer 文案与「继续」按钮一致，含系统弹窗说明
- A11：错误组件不拥有页面导航；栈页面只有返回，模态只有关闭，恢复 CTA 只表达重试/登录/去设置等恢复语义
- A12：自动降级到可操作表单后使用无嵌套动作的紧凑透明表单错误行，目标表单主按钮是唯一恢复动作
- A12：区块首屏完全失败使用无卡片外框的空错态；已有数据刷新失败保留旧数据；分页失败只占用列表尾部
- A13：表单发送/提交/依赖失败在操作点附近使用 `AppFormErrorCard`，字段校验使用 `AppInlineFieldError`；二者必须复用同一透明圆形感叹号错误行，同一失败不得再叠加 Toast、dialog 或第二段弱提示
- A14：错误标题只说明状态；可点恢复动作不在说明或 `user_message` 中重复。可重试播放失败只展示一个“再试一次”CTA，不可重试播放失败不展示伪重试。
- A15：首屏、区块、分页、刷新、动作、登录/权限和媒体错误均有与载体匹配的退出路径，错误组件不复制宿主返回或关闭控件。

## 测试目录约定（按领域服务划分）

- 统一按领域服务划分：禁止 `test/features/`、禁止 `test/cloud/integration/` 顶层
- 集成归属使用它的领域：content 使用 location → `test/cloud/content/location/`、`test/ui/content/entry/`
- 领域与实体使用名词：entry（创作入口）、location、post；禁止 create、publish 等动词
- 验证核心：**交互过程的异常**（权限拒绝、云端超时、加载失败）的 UI 表现；弱化纯 l10n key 存在性测试
- 统一错误语义层需补 `UiErrorSemanticResolver` 的 contract / widget / journey 三类测试

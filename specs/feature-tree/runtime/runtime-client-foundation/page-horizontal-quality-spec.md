# 客户端页面「横向质量维度」规格（跨会话统一验收 · 可扩展）

> **用途**：按 **横向合规项**（非「支柱」命名，避免与后续新增维度绑定死「7」）逐页打勾：**`✓` 已落实**、**`—` 本页不涉及**、**`○` 待审计**；**禁止留空**。  
> **扩展**：后续若有新的横向要求（如无障碍、性能预算），在矩阵中 **追加 P9、P10…**，**不得**与既有维度合并表述。  
> **全量清单**：[`page-horizontal-quality-matrix.md`](./page-horizontal-quality-matrix.md)（按 **领域 × 页面类型** 分列）。  
> **L3 索引**：[`page-horizontal-quality/spec.md`](./page-horizontal-quality/spec.md)。  
> **新增页面**：合入前必须 **新增一行** 并核对 **P1–Pn 当前列**；详见 [`page_horizontal_quality_pr_checklist.md`](../../../gates/page_horizontal_quality_pr_checklist.md)。  
> **全量横向补齐**：按 **9 个独立会话** 执行（S1–S8 各对应 **P1–P8** 之一，**S9** 收口），见 [`page-horizontal-quality/nine-session-rollout-plan.md`](./page-horizontal-quality/nine-session-rollout-plan.md)。  
> **S8（P8）子 L3 /baseline**：[`s8-p8-semantic-token/spec.md`](./s8-p8-semantic-token/spec.md) · [`CR-20260330-012`](../../../changelog/CR-20260330-012-s8-p8-semantic-token-baseline.yaml)（W0–W5 代码波次见该目录 `plan.yaml`）。

## 页面类型（与矩阵列「类型」一致）

| 代码 | 含义 |
|------|------|
| **T1** | 主壳 `IndexedStack` 内一级频道根页（Tab 常驻） |
| **T2** | `GoRouter` 独立全屏路由页 |
| **T3** | `GoRouter` **子路由** / 嵌套 path（挂在父 route 下） |
| **T4** | **模态**全屏（如 `fullscreenDialog`、透明过渡创作入口） |
| **T5** | **无独立 GoRoute**，主要由 `Navigator.push` / 内嵌栈打开 |
| **T6** | **`components/`** 内全屏页或 **跨路由复用骨架**（非业务 `ui/*/pages` 独占） |
| **T7** | **壳内子视图**或 **当前未挂路由的存量页面文件**（须标记后续处理） |

## 横向维度定义（当前 P1–P8）

> **P7 与 P8 分属不同合规面**：**禁止**在规格或 PR 说明里把「断点/多屏布局」与「设计系统语义 token」写成同一项。

| 维 | 名称 | 落实标准（摘要） | 典型「—」不适用 |
|----|------|------------------|-----------------|
| **P1** | **iOS 原生** | 根壳与材质符合 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`；禁止 Material 根 `Scaffold` 违规（与 `ios-native-page-enforcement` 一致）；交互无 Android 泄露 | 纯 `WebView` 内文档内容由外链决定，**壳**仍要 P1 |
| **P2** | **元数据驱动** | 该页主读写 API 的 path/operation 与 DTO 以 **`contracts/metadata` → codegen** 为唯一真相；无手写第二套契约。**逐页是否已达目标态** 以 `specs/gates/metadata_driven_ui_gap_inventory.yaml` 的 `status` 为权威：`compliant`→可标 **✓**；`partial`→标 **○**；`exempt`/无云→ **—**（与清单备注一致） | 纯本地工具页、相机预览等 **无云契约** |
| **P3** | **端云一体化** | 涉及云的领域使用 **`Mock*Repository` + `Remote*Repository`** + `appDataSourceModeProvider`（或等价）切换；禁止 UI 直连裸 HTTP；**`lib/ui`、`lib/app`、`lib/core` 禁止 import `cloud/services/*/mock/`**，域名假数据只在 Mock 层（[`mock_data_cloud_integration_policy.md`](../../../gates/mock_data_cloud_integration_policy.md) + `verify_ui_mock_isolation.py`） | 无网络、纯本地状态页 |
| **P4** | **统一埋点** | 页面级 **`open/close/停留`** 或等价事件进入 **统一观测管道**（`AppLogService` / 后续 Analytics 实现）；或登记 **豁免原因**。**全表面覆盖、欢迎并轨 GoRouter、`pageName` 登记与嵌套 push 约定** 见 L3 [`unified-app-page-access/spec.md`](./unified-app-page-access/spec.md) | 极短 transient 路由页可 **—** 但须在备注说明 |
| **P5** | **组件复用** | 设置表单走 **`SettingsInsetForm*`**；群成员嵌入式搜索走 **`search_embedded`**（`EmbeddedMemberSearchPageShell`，登记 `settings_canonical_manifest`）；对话态半屏走 **`settings_conversation/`**；禁止重复造同类壳 | 强定制全屏沉浸且已登记模板的页面可 **—** |
| **P6** | **深色 / 浅色** | `dual-theme-page-coverage`（S6）：主表面与字色 **双色可用** 或 **登记豁免** | 产品强制单模式（须备注） |
| **P7** | **多屏断点与响应式布局** | 在 **`compact` / `regular` / `expanded`**（及项目登记断点）下 **版式不断裂、可读可点**；优先 **`AppSpacing.responsiveValue`**、**`feedMaxContentWidth`** 等与 **布局/断点** 直接相关的 API；**禁止**为布局再维护一套私有断点 map | 固定纵横比全屏取景（如相机预览）可对 **纯取景区** 标 **—**，**外围壳与控件行**仍须满足 P7 |
| **P8** | **设计系统 · 语义 token** | **间距、字阶、圆角、色、分割线**等须走已登记的 **语义常量 / Theme 扩展 / 组件 token**（如 `AppSpacing.*`、`AppTypography.*`、`CupertinoTheme` 衍生、`settings_semantic_constants` 等）；**禁止**魔法数与「随手 `EdgeInsets.all(13)`」式非语义混用（与 `verify_dart_semantic` 等门禁同向） | 与 UI 无关的纯逻辑页可 **—**；**凡渲染控件的页面极少整体 —** |

**S7 / P7 落实策略（默认 B）**：三档断点均需验收；在 **`expanded`** 下优先使用 **`feedMaxContentWidth`**、`AppSpacing.responsiveValue` 等已登记语义 **约束内容最大可读宽度**，避免平板端无限拉宽单列文本。**默认 A**（仅保证 compact 不断裂）不作为发布口径，除非页面在矩阵备注中登记豁免。

## 与独立工作流映射（便于打勾）

| 主题 | 主要维度 |
|------|-----------|
| iOS 原生壳与门禁 | **P1** |
| 元数据驱动契约 | **P2** |
| 端云一体化 | **P3** |
| 统一埋点 | **P4** |
| 设置表单 / 对话态复用 | **P5**（及与 P1 重叠部分） |
| 双色模式 S6 | **P6** |
| 响应式布局 / 断点 | **P7**（**不含** token 口径） |
| 语义 token / 设计系统 | **P8**（**不含**断点策略） |

## 商用基线、权限与 NFR（本 L3）

| 项 | 结论 |
|----|------|
| **SLO/KPI** | 本 L3 为 **工程治理与 UI 一致性登记**，不单独承诺线上 SLO；各业务 L3 在自身 spec 中定义。 |
| **权限 / 数据生命周期** | 不引入新业务权限与数据留存变更；仅约束 **页面合规登记与门禁**。 |
| **灰度 / 回滚** | 矩阵与脚本变更通过 **PR revert**；`verify_page_horizontal_quality_matrix.py` 可从 `gate_repo.sh` 临时摘除（应急）。 |
| **观测** | 合规进度以 **矩阵列 `✓`/`○` 比例** 与兄弟 L3（S6、iOS 壳、元数据清单）交叉引用为人工/半自动观测。 |

## 强制校验（v1 流程 → v2 自动化）

| 阶段 | 要求 |
|------|------|
| **v1** | 每个涉及页面的 PR **必须** 更新 `page-horizontal-quality-matrix.md` 对应行的 **当前 P 列**；使用 `specs/gates/page_horizontal_quality_pr_checklist.md` 自检 |
| **v2** | `scripts/verify_page_horizontal_quality_matrix.py`（路径存在性 + **P1–P8** 符号）+ `scripts/verify_page_matrix_scan_complete.py`（磁盘↔矩阵↔缺口清单 **无漏页**）；已接入 `make gate` 的 app 段；本地快检 **`make verify-app-page-horizontal-quality`**；列数扩展时同步改脚本 |

## 验收（总会话）

- 矩阵 **每一行** 当前 **P1–P8** 均为 **`✓` / `—` / `○`**（`○` 仅作待审计基线，**发布前**应收敛为 `✓` 或 `—`）；`—` 须有备注或指向豁免条款。  
- 新增页面 **无漏登记**。  
- **P7** 与 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.7 **一致**（布局/断点面）。  
- **P8** 与既有 Dart 语义 / 设置语义门禁 **同向**，不得在页面内引入新的魔法数体系。

# L3 Story：统一应用页级埋点（unified-app-page-access） (`unified-app-page-access`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `pageVisitId` 对齐，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “统一应用页级埋点（unified-app-page-access）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 统一应用页级埋点（unified-app-page-access）

- **P4（横向质量）**：页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `pageVisitId` 对齐。

<a id="req-002"></a>
### REQ-002 P4（横向质量）：页面级 open / return /（可选）停留 进入 AppLogService 统一管道，与 AppTraceContextStore 的 sessionId / pageVisitId 对齐

- **P4（横向质量）**：页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `pageVisitId` 对齐。
- **问题**：欢迎流使用 **独立 `MaterialApp(home: WelcomeScreen)`**，不在 **`GoRouter` 根 `NavigatorObserver`** 上，只能靠页面 **手写** `writeAppPageAccessOpen/Return`；全站 **`pageName`** 对非 Tab 路径多为 **`route_unknown`**，分析不可读。
- **页内细粒度点击流**（如技能中心 `skill_center_action`）的 schema 统一（可在后续切片要求 **复用当前 `pageVisitId`**，见 `design.md`）。
- **metadata-first**：**`/welcome`** 仅通过 **`app_routes.yaml` → codegen**，禁止手写第二套 path 常量于业务页。
- **禁止双计**：同一用户可见「表面」在 **open** 上 **只打一次**；Tab 与全屏栈边界以 **`isShellTabLocation`** 与现有 **`MainAppShell`** 逻辑为准，**不重复** welcome 与 Tab。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 统一应用页级埋点（unified-app-page-access）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“统一应用页级埋点（unified-app-page-access）”对应的公开行为。
- THEN **P4（横向质量）**：页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `pageVisitId` 对齐。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

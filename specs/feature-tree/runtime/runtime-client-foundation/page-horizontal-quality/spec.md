# L3 Story：页面横向布局质量 (`page-horizontal-quality`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “页面横向布局质量”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 页面横向布局质量

- 在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达。

<a id="req-002"></a>
### REQ-002 页面装配保持强类型

- 页面文件不得用 `dynamic`、`Map<String, dynamic>` 或版本化 `Current/V2` 命名承载展示与观测状态；可扩展观测属性使用 `Map<String, Object?>`，路由参数使用明确可空类型。

<a id="req-003"></a>
### REQ-003 页面对象契约表达读模型归属，不表达 HTTP 直连

- `page_object_contract.yaml` 的 `query_slices` 表达数据血缘与读模型归属，不表示该页面直接调用被认领对象的 HTTP 路由。
- 跨域 hydration 是合规形态：页面认领的对象可以只提供内部特征或读模型，真实读路径由另一个域的 App 面 operation 承载。
- 页面认领对象的必需产物是 presentation 实现，不包含 clientContract；被页面认领却没有 clientContract 的对象不得判为缺口。
- 认领 `recommendation.recommendation_feature_profile_view` 的页面即属该形态，其真实读路径由 `content.intersection_visit_state` 与 `content.post` 的 App 面 operation 承载。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面横向布局质量

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“页面横向布局质量”对应的公开行为。
- THEN 在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 页面强类型扫描无例外

- GIVEN App 页面清单由 canonical page matrix 生成。
- WHEN 执行页面 A/B/C 治理门禁。
- THEN A、B、C 三类违规均为 0，且不读取默认 allowlist 掩盖页面动态类型或历史命名。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

# L3 Story：S8 — P8 设计系统语义 token 全页落实 (`s8-p8-semantic-token`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向），
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “S8 — P8 设计系统语义 token 全页落实”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 S8 — P8 设计系统语义 token 全页落实

- 横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向）。

<a id="req-002"></a>
### REQ-002 横向质量矩阵 P8 要求：间距、字阶、圆角、色等走 语义 token，禁止魔法数与非语义混用（与 verify_dart_semantic.py 同向）

- 横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向）。
- 断点与版式由页面横向布局 Story 负责；本 Story 只验收语义 token，不把断点策略并入同一验收边界。
- **小趣 runtime 垂类特判、字符串硬编码协议**：不适用本 L3；若改动触及助手 UI，仍须遵守 [assistant-run-learning design](../../../assistant-run-learning/design.md)，不得借 token 改造引入新特判。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 S8 — P8 设计系统语义 token 全页落实

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“S8 — P8 设计系统语义 token 全页落实”对应的公开行为。
- THEN 横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向）。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 S8 — P8 设计系统语义 token 全页落实 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“S8 — P8 设计系统语义 token 全页落实”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

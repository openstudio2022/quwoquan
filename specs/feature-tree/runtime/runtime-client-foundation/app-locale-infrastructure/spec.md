# L3 Story：App 语言区域基础设施 (`app-locale-infrastructure`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望通过 ARB 与 flutter gen-l10n 生成本地化资源，并在 locale 切换后保持页面文案一致，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “App 语言区域基础设施”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 App 语言区域基础设施

- 通过 ARB 与 flutter gen-l10n 生成本地化资源，并在 locale 切换后保持页面文案一致。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 App 语言区域基础设施

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“App 语言区域基础设施”对应的公开行为。
- THEN 通过 ARB 与 flutter gen-l10n 生成本地化资源，并在 locale 切换后保持页面文案一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 App 语言区域基础设施 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“App 语言区域基础设施”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 英文本地化只有骨架，切到 en 后近九成文案仍是中文

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 `app_en.arb` 的 590 个 key 中 528 个仍是 `TODO: translate`（89.49%），对应生成的 `app_localizations_en.dart` 逐条一致；中文侧 0 处 TODO，完整。这意味着 `GWT-001` 声称的「locale 切换后保持页面文案一致」在 en 下并不成立——切到英文后绝大多数界面仍显示中文，不是缺翻译的观感问题，而是本地化能力事实上只有中文一条腿。这是面向英文市场的发布阻断项，不是代码整洁度债务。
- 完成判定：`GWT-001` 在 `en` locale 下成立——`app_en.arb` 不再包含任何 `TODO: translate`，且 user_acceptance 层有真实测试 `spec_ref` 断言切换到 en 后关键路径页面不出现中文字面量。翻译缺口清零前不得把本 OPEN 降级为 `track`。
- 度量口径：`rg -c 'TODO: translate' quwoquan_app/lib/l10n/app_en.arb` 与 arb 的 key 总数相比；生成物 `app_localizations_en.dart` 必须与 arb 同步，不得单独改生成物充数。

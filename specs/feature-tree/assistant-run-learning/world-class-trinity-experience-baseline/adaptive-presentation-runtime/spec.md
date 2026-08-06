# L3 Story：自适应展示 (`adaptive-presentation-runtime`)

> 所属能力：[小趣统一体验](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为在不同设备和场景使用小趣的用户，我希望回答能按内容呈现卡片、图文、时间线、比较、来源和确认动作，同时在设备能力不足时仍能读到完整核心答案。

## 2. 范围与非目标

### In Scope

- Skill 云端语义模板、结构化填槽、服务端验证、持久展示文档与 Flutter 原生自适应渲染。
- 设计 token、媒体引用、typed action、无障碍和 Markdown/纯文本降级。

### Out of Scope

- 云端 Flutter/HTML/JavaScript、任意 CSS/像素布局、任意客户端路由或领域页面代码复用。

## 3. 行为要求

### REQ-001 模型只能选择 Skill 允许的模板并填充数据

- 模板与输入 schema 必须来自已激活的不可变 Skill Package。
- 服务端必须验证模板、数据、节点预算、媒体、动作和客户端能力后才形成展示事实。

### REQ-002 客户端以安全语义节点自适应渲染

- App 必须用设计系统组件渲染受支持的容器、内容、结构和交互节点，并按屏幕、平台、主题、字体、动效与离线能力选择变体。
- 样式只接受 canonical 语义 token；图片与动作只接受 canonical asset/operation 引用。

### REQ-003 未知或非法展示确定性降级

- 未知节点、摘要不匹配、非法数据或媒体失败不得导致白屏、崩溃或核心答案丢失。
- App 必须使用同一展示文档中的 Markdown 或纯文本降级并记录降级原因。

## 4. 契约引用

- object / projection：`AssistantPresentationTemplate`、`AssistantPresentationSelection`、`AssistantPresentationDocument`、`AssistantPresentationNode`
- event / metric：`presentation_snapshot`、`presentation_patch`、`presentation_commit`、`assistant_presentation_fallback`
- ActionIntent：闭集 `Navigate`、`ApproveTool`、`ExecuteDeviceAction`、`ProvideInput`，每类只携带自己的 typed 子契约，未知 kind、过期、digest mismatch 与 replay 均零执行。
- operation：`ApproveAssistantToolUse`、`SubmitDeviceActionReceipt`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 旅行回答跨端自适应

- GIVEN 旅行 Skill 生成包含行程时间线、天气风险、地点图片与来源的数据。
- WHEN 窄屏和宽屏客户端渲染同一展示文档。
- THEN 两端使用各自支持的语义变体并保留相同事实、动作和引用。
- AND 大字体、深浅主题与减少动画均保持可访问。

<a id="gwt-002"></a>
### GWT-002 旧客户端安全降级

- GIVEN 已激活模板包含客户端不支持的节点。
- WHEN 客户端接收终态展示文档。
- THEN 客户端显示完整 Markdown 或纯文本答案且不执行未知动作。
- AND 降级被结构化观测。

## 6. 依赖

- 前置要求：Skill Package、canonical media asset、operation reachability 与设计系统可用。
- 上游事实：Presentation Selection、surface capability 与终态答案。
- 下游结果：Presentation Document、原生 Widget 与交互 continuation。
- 父级设计：`DEC-004`

## 7. 开放事项

### OPEN-001 Android/iPhone 真机 Adaptive Presentation 验收尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺可启动的受管 Remote 环境，以及 Android/iPhone 真机上的 Adaptive Presentation 跨端执行收据。服务端模板选择、schema/action/media/capability 校验、持久 `presentation_snapshot/commit`、SSE revision 投影、Flutter Renderer Registry、typed action、未知节点非空 Markdown fallback、语义/窄宽屏/大字体 local contract 与 fallback 遥测已经接线，真实 Mongo Worker API integration 和 Patrol UAT 定义也已补齐。Remote 环境受 Provider material/readiness 阻断，本机也没有 Android/iPhone 真机，因此不能把 Flutter local contract、iOS simulator 或被跳过的 Patrol 当成跨端完成。
- 完成判定：同一候选 baseline 在 Android/iPhone 真机执行合法文档原生渲染、非法文档非空 fallback、未知 action 零执行、light/dark、大字体、减少动画、宽窄屏和离线恢复；fallback 指标与告警可回读，direct `spec_ref` 保持有效。

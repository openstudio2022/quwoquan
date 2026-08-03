# L3 Story：原生工具调用与模型档位路由 (`native-tool-calling-model-routing`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为向小趣提出复杂问题的用户，我希望难题由更强的模型档位承接、简单问题快速返回，并且单一模型故障时自动切换而不是直接失败，从而获得既稳定又响应及时的回答。

## 2. 范围与非目标

### In Scope

- 模型提供方原生工具调用协议
- 按运行阶段与问题类型选择模型档位
- 模型不可用时的档位降级链

### Out of Scope

- 自建、微调或蒸馏模型
- 模型侧内容安全审核与合规过滤
- 工具的业务实现

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 工具选择使用模型原生工具调用协议

- 助手请求模型选择工具时必须使用提供方的原生工具调用协议，工具定义必须来自工具元数据真相源。
- 不得依赖模型回答正文中的约定 JSON 键名推断工具选择。
- 提供方不支持原生工具调用时必须显式降级为结构化输出协议，且工具选择语义与原生协议一致。

<a id="req-002"></a>
### REQ-002 模型档位由运行阶段与问题类型决定

- 模型档位必须由运行阶段与问题类型共同决定，档位定义与模型标识只能来自环境配置。
- 不得在代码内固定模型标识或采样参数。

<a id="req-003"></a>
### REQ-003 模型不可用时按声明顺序降级

- 主档位模型超时或不可用时必须按配置声明的顺序降级到下一档位并继续该次运行。
- 全部档位均不可用时必须返回 canonical 模型不可用失败，不得合成回答或返回空答案。
- 已经开始向用户流式输出后发生失败时不得静默改写已输出内容。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/errors.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_tool_metadata/schema.yaml`
- object：`quwoquan_service/services/assistant-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 复杂问题走强档位并以原生协议选择工具

- GIVEN 环境配置声明了快速档位与强推理档位两个模型档位
- WHEN 用户提交需要外部检索的复杂问题
- THEN 推理阶段使用强推理档位模型并以原生工具调用协议返回工具选择
- THEN 提交给模型的工具定义来自工具元数据而非回答正文约定键名
- THEN 代码内不存在固定的模型标识

<a id="gwt-002"></a>
### GWT-002 主档位不可用时降级而不失败

- GIVEN 主档位模型返回超时或不可用
- WHEN 用户提交问题
- THEN 该次运行降级到下一声明档位并产生可展示回答
- THEN 全部档位不可用时返回 canonical 模型不可用失败且不产生回答事实

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：环境配置声明的模型档位与外部 Provider 绑定。
- 下游结果：本 Story 声明的 GWT 可观察结果，供技能路由与编排消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 受管 Provider 原生工具调用验收尚未闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺受管 Provider 对 `tools/tool_choice`、三档模型绑定、超时降级和流式失败边界的环境 conformance 回执，因此本地实现不能代替生产能力声明。
- 已完成实现：模型请求携带 canonical Tool metadata 生成的强类型工具声明。Provider capability 决定原生协议或结构化输出降级。档位按 stage、problem class 与 search intensity 决定，模型 ID 只从环境配置读取。不可用或超时仅向下逐档降级，流式输出开始后禁止切换。
- 已完成本地证据：`GWT-001/GWT-002` 直连 local contract 已覆盖原生工具调用、参数 delta 组装、结构化降级、确定性档位路由、全部档位失败和流式开始后停止降级。
- 完成判定：在同一受管候选上复验 native tool capability、fast/balanced/reasoning 配置、主档不可用、全部档位不可用和流式中断，并取得 Prod 外部 Provider conformance 回执。

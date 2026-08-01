# L3 Story：领域技能路由与提示按需加载 (`skill-progressive-disclosure-routing`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为向小趣提问的用户，我希望出行、天气、本地生活这类问题被交给对应的领域技能处理并给出该领域应有的答案结构，而不是所有问题都走同一个通用搜索。

## 2. 范围与非目标

### In Scope

- 策略允许集合内的领域技能选择
- 技能索引常驻与技能提示正文按需加载
- 技能声明的工具策略与调用预算生效
- 私有技能目录的对象归属、账号授权投影与 fail-closed Reader

### Out of Scope

- 用户自定义技能与第三方技能订阅
- 技能内部的答案排版规则
- 主动订阅技能的调度与投递门禁

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 技能选择在策略允许集合内进行

- 策略发布必须决定本次运行允许的技能集合与预算上限，具体技能必须在该集合内选择。
- 运行创建点冻结的策略 `releaseDigest` 与灰度分组不得被技能选择改写。
- 允许集合内没有匹配技能时必须落到声明的通用技能，且该通用技能同样具备完整检索与引用能力。

<a id="req-002"></a>
### REQ-002 技能提示正文按需加载

- 技能索引必须常驻可见，技能提示正文必须仅在该技能被选中后加载。
- 不得把技能提示资产标识当作提示正文提交给模型。
- 技能资产缺失时必须返回结构化失败，不得以资产标识或空字符串继续运行。

<a id="req-003"></a>
### REQ-003 技能定义只有一个真相源

- 反应式技能与主动式技能必须由同一份技能清单声明，包含其工具策略与调用预算。
- 不得在代码内维护第二套技能名单、工具策略或预算常量。

<a id="req-004"></a>
### REQ-004 技能目录按可信账号读取授权状态

- 技能目录只向已验证账号主体返回，并只读取该账号自己的授权事实。
- 授权存储缺失或读取失败时必须返回 canonical unavailable 终态，不得把未知授权状态当作未授权、已授权或公共目录继续返回。
- 技能目录响应包含账号授权状态，因此必须按敏感私有数据处理，不得由匿名请求或客户端身份 header 读取。

<a id="req-005"></a>
### REQ-005 技能目录由独立对象单轨拥有

- `SkillCatalog` 必须独立拥有 fields、`ListSkills` operation、typed errors、application query、catalog source 与 SkillConsent Reader port。
- `AssistantRun`、`AssistantSession` 不得保留目录 response type、operation、HTTP route、查询方法或错误 emitted_by；HTTP path `/assistant/skills` 保持不变。
- canonical manifest 只负责运行技能展示元数据，非运行技能的平台能力入口只在 SkillCatalog source 内声明；不得在查询服务或 handler 追加第二套目录。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_skill_manifest/schema.yaml`
- object：`quwoquan_service/services/assistant-service/resources/skills/assistant/assistant_session/schema.yaml`
- operation：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_policy_release/operations.yaml`
- catalog object：`quwoquan_service/services/assistant-service/contracts/assistant/skill_catalog/object.yaml`
- catalog operation：`quwoquan_service/services/assistant-service/contracts/assistant/skill_catalog/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 出行问题路由到出行技能

- GIVEN 策略发布的允许技能集合包含出行技能与通用技能
- WHEN 用户提交一个行程规划问题
- THEN 该次运行选中出行技能并按其声明的工具策略与调用预算执行
- THEN 运行创建点冻结的策略 `releaseDigest` 与灰度分组保持不变

<a id="gwt-002"></a>
### GWT-002 技能提示资产不得以标识代替正文

- GIVEN 某技能声明了提示资产
- WHEN 该技能被选中并组装模型请求
- THEN 模型请求携带该资产的正文内容
- THEN 模型请求不包含资产标识字符串
- THEN 资产缺失时返回结构化失败而不是继续运行

<a id="gwt-003"></a>
### GWT-003 技能目录账号隔离与授权读取失败关闭

- GIVEN 已验证账号拥有一条有效技能授权事实
- WHEN 该账号读取技能目录
- THEN 目录只使用该账号的授权事实标记对应技能
- AND 匿名请求返回 canonical unauthorized
- AND 授权存储缺失或读取失败返回 canonical unavailable，不返回目录或合成授权状态

<a id="gwt-004"></a>
### GWT-004 技能目录对象单轨归属

- GIVEN metadata、服务实现与测试树已加载
- WHEN 检查 `ListSkills` 的契约与路由归属
- THEN canonical operation 只有 `assistant.skill_catalog.ListSkills`
- AND AssistantRun/AssistantSession 不再包含目录 fields、operation、handler 或 query
- AND catalog source 或 SkillConsent Reader 任一不可用时返回 SkillCatalog 对象拥有的 typed unavailable

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：技能清单声明与策略发布的允许集合、灰度分组。
- 下游结果：本 Story 声明的 GWT 可观察结果，供编排与工具执行消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 主动技能的话术仍未纳入按需加载

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍缺主动订阅技能的提示资产。主动技能的判定、展示名与工具策略已经统一由技能清单声明，但其推送话术仍由代码内的分支拼装，无法像反应式技能那样按需加载与独立调整。
- 完成判定：主动订阅技能的话术改由清单声明的提示资产提供，并由测试断言资产正文进入模型请求。

# L3 Story：协同召回 (`collaborative-recall`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望从符合隐私和最小样本约束的 itemCF、Swing 与 u2i 信号生成候选并保留召回理由，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “协同召回”的输入、可观察主路径、失败语义以及与父能力的交接。
- 行为共现离线物化。
- i2i/u2i 召回源与多路召回配额融合。
- replay 评估与回滚层。
- 离线物化作业和 replay 评估脚本按后续数据工程切片补齐。
- feed 读路径同步共现计算。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 协同召回

- 从符合隐私和最小样本约束的 itemCF、Swing 与 u2i 信号生成候选并保留召回理由。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 协同召回

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“协同召回”对应的公开行为。
- THEN 从符合隐私和最小样本约束的 itemCF、Swing 与 u2i 信号生成候选并保留召回理由。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 协同召回 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“协同召回”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

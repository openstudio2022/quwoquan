# L3 Story：交集句主谓宾统一表达

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `intersection-sentence-unification`

## 功能说明

把"交集"在所有紧凑 / 列表 surfaces 的展示统一收敛为「主谓宾一句话」表达，端只读云侧 `IntersectionReason.primaryText`，禁止本地拼装事实。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17。

句式：`主语[数量 N 位 + 关系限定] + 谓语[行为动词] + 宾语[对象]`。

## 范围

- 端侧统一交集句组件（收敛现有 `IntersectionReasonChip`）：单句、蓝色、单行省略；**仅**消费 `primaryText`（禁止 displayText 回退）。
- 两类 surface 句式层次：紧凑 surface 严格一条结论句、无副句；列表入口允许结论句 + 至多一条灰色辅助说明 + 「查看更多」。
- 概念合规：事实通道禁止「朋友/好友/收藏/同趣」；affinity 明确标注「推荐」。

## Out of Scope

- 云侧排序 / 语义压缩 / 埋点回流（仅端侧消费 `primaryText`）。
- 第二套端侧拼接交集文案。

## 验收标准概要

- A1：紧凑 surface 有且仅一条交集句，无多条 / 无标签列表 / 无浮层 / 无三行。
- A2：无来源 / 无可展示结论句 → 不展示（不占位、不造假）。
- A3：mock 与展示文案不含「朋友/好友/收藏/同趣」违禁词（事实通道）。

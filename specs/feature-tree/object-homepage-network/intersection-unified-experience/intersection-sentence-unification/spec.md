# L3 Story：交集句主谓宾统一表达

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `intersection-sentence-unification`

## 功能说明

把"交集"在所有紧凑 / 列表 surfaces 的展示统一收敛为「主谓宾一句话」表达，端只读云侧 `IntersectionReason.primaryText`，禁止本地拼装事实。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17。

句式：`主语[关系限定 + 代表人 + 人数] + 谓语[真实行为动词] + 宾语[可点击 typed target]`。示例：`联系人林清越等3人赞过和评论过《川西雪山和校园摄影路线》`。

## Display Contract

- `primaryText` 只由云侧产出；App 只做 `displayReadyIntersectionReason` 复核和 fail-closed，不合格不展示、不补句。
- `join(primarySpans.text) == primaryText` 必须成立。
- 数字主语必须有 `representativeActor`：代表人 target 为 `user`，且有具体 `relationLabel`；不能只写 `4位共同好友`、`8人都来这里互动过`、`你和这里`。
- 宾语必须落到可路由 `IntersectionTarget`：`user/circle/homepage/post/task`。内容类对象用 `post` + `workBrowser`，圈子/实体/人分别映射到对应对象页。
- 人数 span 只有在 `actorEvidenceCompleteness=complete` 时可点击，route 固定 `myIntersections`，并能逐人下钻。
- 禁止主句 raw stats 和泛词：`2赞 1评 1转`、`同读者`、`相近主题的长文`、`TA的内容`、`相关圈子`、`我的连接`、`我的影响力`。
- `start_companion` 必须绑定同一条 `coWishlistedEntity` 证据和可承接 target；没有真实 co-wisher / 承接页时不展示行动入口。

## 范围

- 端侧统一交集句组件（收敛现有 `IntersectionReasonChip`）：单句、蓝色、单行省略；**仅**消费 `primaryText`（禁止 displayText 回退）。
- 两类 surface 句式层次：紧凑 surface 严格一条结论句、无副句；列表入口允许结论句 + 至多一条灰色辅助说明 + 「查看更多」。
- 概念合规：事实通道禁止「朋友/好友/收藏/同趣」；affinity 明确标注「推荐」；我的主页/用户主页/实体主页/圈子主页统一使用「我的交集」口径。

## Out of Scope

- 云侧排序 / 语义压缩 / 埋点回流（仅端侧消费 `primaryText`）。
- 第二套端侧拼接交集文案。

## 验收标准概要

- A1：紧凑 surface 有且仅一条交集句，无多条 / 无标签列表 / 无浮层 / 无三行。
- A2：无来源 / 无可展示结论句 → 不展示（不占位、不造假）。
- A3：mock、alpha/beta/gamma seed 与真实服务响应不含「朋友/好友/收藏/同趣」违禁词（事实通道）。
- A4：所有可见交集句满足云侧 SVO、typed object、representativeActor、actorEvidence 与 actionHints 同源合同；否则云侧清空、端侧 fail-closed。

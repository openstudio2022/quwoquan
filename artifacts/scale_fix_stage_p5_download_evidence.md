# Phase C/P5 阶段证据(1):全新批次 download 阶段(RC3 修复后)逐项验证

批次:`创作冒烟试跑-36665c88__p5_sichuan_20260630`(task=旅行/地域/四川省/景区/创作冒烟试跑,
3 实体 九寨沟/峨眉山/都江堰,3 车道 homepage/article/image,composer-2.5,concurrency=2/max-workers=2)。

`scaled-e2e run` slice1(bounded 900s)实际 92s 走完 download,PAUSED 于 agent checkpoint
`build_homepage`(exit 10)。download 阶段逐项证据如下。

## 1. RC3 内联图抽取端到端验证通过

去哪儿游记源单元 `sources/su_c0b0e69bf3c8f4a51ad9`(url=touch.travel.qunar.com/youji/7900288):
- `source.clean.md` 含 **346 个 `![source image]` 内联图占位** → RC3 lazy data-* 抽取在真实页端到端有效
  (修复前几乎为 0)。
- `meta.assetFunnel`:candidateCount=**1502**,keptCount=**0**,droppedCount=1502,
  `dropReasonCounts={"rights":1502}`(imageRights: missing required field license)。
  → qunar 内联图**无 per-asset 许可**,被 rights 硬门正确全部拒绝(不发布未授权图)。

## 2. 三类解耦路由 + 来源择优 + 许可分流(逐车道)

| 车道 | 来源 | use/license | 判定 |
|---|---|---|---|
| homepage | 维基百科 home_wikipedia / 景区官网 home_official | factual_reference_only | 百科择优;`home_baidu_baike` 被实体百科择优**拒绝**(log: Rejected source isolated .../home_baidu_baike) |
| image | image_coll 开放图集 ×6(九寨沟/峨眉山/都江堰 各 1-2) | **licensed_adaptation**,CC BY 2.0 / CC BY-SA 3.0/4.0 | ✓ 专业图库一源一作品,均带开放许可 |
| article | 维基导游 wikivoyage(focus=strong 0.46/0.60)、去哪儿攻略峨眉山(strong 0.15/0.17)、九寨沟+三星堆(supporting 0.13)、景区官网(supporting 0.17) | 全部 factual_reference_only | on-entity 文章存在;discovery 噪声(318自驾/特种兵四地/渝蜀贵自驾)被正确判 **off_entity**(score≈0.003-0.06)并降级 |

## 3. 真实 findings(诚实记录,非假装通过)

### F1(P0,已确认登记 backlog 的 RC4 同源):article 图文混排与图片许可冲突

qunar 图文游记是天然图文混排,但**无 per-image 许可**,内联图被 rights 门全拒 → 整篇降级
`factual_reference_only`(文字参考),无法作为"图文混排可发布底稿"。后果:article carrier 无可发布
的同源图文底稿(image 配额由 image 车道开放图集满足,article 则倾向长文文字或缺稿)。
**这与"图片同源 + 不发未授权图"是一致取舍**:图片作品走专业开放图库(已验证 6 个 CC 图集),
article 若要发布须走长文文字(≥600 有标题)或找带 per-image 许可的图文源。

### F2:discovery 相关性噪声

article 车道混入 off-entity 游记(此生必驾318、特种兵四地5日游、渝蜀贵自驾穷游),
被 entityFocus 门正确判 off_entity(score 0.003-0.06)并降级 factual_reference_only,不会污染产出;
但**上游 discovery 仍把不相关游记选为候选**,浪费抓取且降低 on-entity 命中密度。属上游召回质量问题。

### F3:authoring checkpoint 需 managed agent 驱动

`scaled-e2e run` 在 `build_homepage` agent checkpoint PAUSED(exit 10),未在 run 内自动驱动
homepage 正文创作。需 managed-agent/self-heal 续跑驱动(见下一阶段)。

## 结论

download 阶段:RC3 抽取、三类路由、百科择优、开放图库许可、su_* 源单元布局、off-entity 检测、
rights 硬门 **均按设计正确工作**。剩余阻断在 authoring 驱动稳定性(F3)与上游 discovery 相关性(F2),
以及 article 图文混排-许可取舍(F1,已在 backlog)。

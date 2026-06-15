# data-content-compose

用途：根据 `compose_brief.json` 生成单篇内容。这里是唯一允许写用户正文的步骤。

> fanout 模式下，这是 **per-ref worker 的创作内核**：worker 把租到的单 ref lease packet 交给一个 cloud agent / Subagent，仅创作该 ref 正文并满足 `ref_review_gate.passed`，严格 single-ref 隔离（禁读同批其它文章正文作底稿）。

## 输入

- `compose_brief.json`
- 下载阶段的真实 sources
- `sopExampleRef`
- 可用素材清单

## 写作要求

1. 严格遵守 `compose_brief`：
   - `creator` 决定公开作者口吻和可声明身份。
   - `structure.required` 必须全部覆盖。
   - `mustIncludeFacts` 必须逐项在正文或图注中体现（含地域/季节注入的条件 facts）。
   - `forbiddenPhrases` 任何一个都不得出现。
   - `imagePlan` 决定 `:::figure` / `:::gallery` 位置和版式（含地域/季节注入的图位）。
   - `conditionContext`：若存在，正文里的地域专有现象（高原反应、潮汐、雪线等）只能落在 `conditionContext.region` 授权的地域，季节描述只能落在 `conditionContext.season`；缺省时不得臆造任何地域/季节专有事实。`packing/riskNotes/crowdNotes` 应自然融入正文，不堆砌成清单段。

2. 输出必须是 QWQ Rich Markdown：

```markdown
---
title: ...
template: journal
fontPreset: clean
articleMarkdownVersion: qwq-rich-md/1
---

# 标题

:::figure id="cover" layout="fullWidth" caption="..."
asset://cover
:::
```

3. 推荐/内部字段不得写进正文：
   - `qualityScore`
   - `templateId`
   - `routingReason`
   - `coldStartBoost`
   - `isSystemBuiltin`

4. 标签和实体引用必须自然出现，不得使用独立“标签：”段。

## 输出

写入 produce compose result，字段至少包括：

- `topicId`
- `title`
- `summary`
- `articleMarkdown`
- `entityRefs`
- `tagRefs`
- `assets`
- `articleRenderProfile`
- `template`

## 自检

- 是否像真实作者写的内容，而不是运营稿。
- 是否覆盖专业事实项。
- 是否符合作者 `mustNotClaim`。
- 是否有足够图片槽和图注。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-content-compose` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

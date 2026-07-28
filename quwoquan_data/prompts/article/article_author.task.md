<task>
# 写作任务：{{title}}

- 冻结发布标题: `{{title}}`；`draft.article.md` 首行 H1 必须逐字一致，禁止另造标题导致路由、frontmatter 与 manifest 分叉。
- ref: `{{ref}}` ｜ 类型: `{{kind}}` ｜ 载体: `{{carrier}}` ｜ 模板: `{{template_id}}`
- 署名口吻: {{byline}}
- 字数区间: {{word_count_min}}–{{word_count_max}} 字（去空白）
{{creator_lock_line}}
{{primary_entity_contract_line}}

{{creative_brief_block}}

{{persona_block}}

{{writing_intent_line}}

{{narrative_block}}

{{base_source_line}}

{{banned_terms_line}}

{{opening_guidance_block}}
</task>

{{> _shared/partials/figure_group_contract.md}}

<documents>
{{base_draft_block}}

{{numeric_whitelist_block}}

## 必须覆盖的事实
{{must_include_facts_block}}

{{section_intents_block}}

{{evidence_block}}

## 可用配图素材（asset:// 只能引用下方 assetId；连续图已合并为 figuregroup 占位）
{{assets_block}}
</documents>

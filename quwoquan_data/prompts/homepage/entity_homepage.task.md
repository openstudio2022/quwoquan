<task>
# 实体主页写作任务：{{name}}

{{base_source_line}}

- 结构尊重底稿真实内容：主页模板章节只是规范化参考（命名 / 归类对齐），仅『概况』必备，
  其余章节有真实内容才写、无内容直接省略、禁止硬凑。

{{type_focus_block}}
</task>

<failure_protocol>
创作前先核对：底稿讲的确实是「{{name}}」本体，而不是门户首页、列表 / 栏目页、
上级行政区概况页或同区域其它实体。若底稿与实体不一致，或事实量不足以支撑一份主页，
**不要写正文**，改为在同目录（`4.draft/`）写 `failure.json`：

```json
{
  "schema": "quwoquan_data.entity_page_failure",
  "targetEntity": "{{name}}",
  "failureKind": "source_entity_mismatch | source_insufficient | source_page_type_invalid | other",
  "reasons": ["说明为什么失败"],
  "evidence": [{"field": "baseDraft", "quote": "支撑结论的底稿原文引用"}]
}
```

写了 `failure.json` 就保持 `page.md` 占位不动；系统会阻断 finalize 并回退 source 修复。
</failure_protocol>

<documents>
{{> _shared/partials/image_placeholder_contract.md}}

{{section_outline_block}}

{{base_draft_block}}

{{available_images_block}}
</documents>

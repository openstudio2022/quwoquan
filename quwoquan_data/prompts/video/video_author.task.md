<task>
- 内容 ref: `{{content_ref}}`
- 主实体: `{{entity_name}}`
- 分段数量: {{segment_count}}
- 写入脚本: `{{video_script_path}}`
- 写入元数据: `{{draft_meta_path}}`

`video_script.json` 必须严格为：
```json
{"title":"不超过80字","caption":"不超过300字","scriptLines":["每段一句"]}
```
`scriptLines` 必须恰好 {{segment_count}} 条。

`draft_meta.json` 必须至少包含 `generator=agent`、真实 `model`、`citedSourcePaths`、`createdAt`、`updatedAt`；运行标识由控制器在 Agent 成功后补齐。
</task>

<source_frames>
{{source_frames_json}}
</source_frames>

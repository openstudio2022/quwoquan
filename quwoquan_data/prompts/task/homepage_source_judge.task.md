<task>
# 底稿来源判别任务：{{target_entity}}

- 目标实体：**{{target_entity}}**（类型：{{entity_type}}；登记别名：{{aliases_line}}）
- 待判来源：`{{unit_ref}}`
- 判别后把 verdict JSON 写回该来源目录的 `source.judge.json`。
</task>

<documents>
## 来源元数据

{{source_meta_block}}

## 确定性预筛线索（仅供参考，以内容证据为准）

{{prescreen_block}}

## 正文首屏摘录

```
{{head_text_block}}
```
</documents>

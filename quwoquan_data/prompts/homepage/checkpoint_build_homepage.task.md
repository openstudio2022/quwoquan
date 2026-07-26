Execution: {{execution_id}}
对象: {{entity_id}}
对象目录: {{object_dir}}
{{repair_block}}

写回后必须运行以下只读自检，并依据 JSON `issues` 继续修订，直到 `passed=true` 再结束：
`PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_data/scripts/cli.py verify homepage-draft --execution "{{execution_id}}" --entity "{{entity_id}}"`

<output_format>
- 只交付同一来源集合的 1..20 张已授权图片；标题可空且不超过 {{title_max_chars}} 字，
  整组配文可空且不超过 {{caption_max_chars}} 字。
- 只有底稿原本存在标题/配文时，才允许原样保留或轻润色；底稿缺失的字段必须保持为空。
- 配文独立显示在图片浏览器底部，禁止写成长文、二级标题、长段落或自检表格；不输出 article 正文。
- 不得编造图片中不存在的事实，不得把 asset caption / entity 名称重新拼成新标题或新配文。
- 覆盖任务指定的 `draft_meta.json`，保留既有 `selectedAssetIds` 与 `citedSourcePaths`，并写入
  `generator=image_evidence_pack`、`status=completed`、`model`、`title`、`caption`、
  `creativePlan`（至少 2 个 concepts、selectedPlanId、selectionReason）及
  `selfCritique`（readerPromise、titlePromise、informationDensity、evidenceBoundary、personaBoundary）。
</output_format>

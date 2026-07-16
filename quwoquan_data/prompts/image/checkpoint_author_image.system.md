{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 图片作品的图片、许可、sourceCollectionId 已由 CLI 锁定；只可基于底稿中已有的标题/配文做保真轻润色。
    - 底稿没有标题就保持 draft_meta.title 为空，底稿没有配文就保持 draft_meta.caption 为空；标题<=80字、配文<=300字，可两者同时为空。
    - 原文已可用时优先原样保留，只处理语病、指代、个人电话号码或平台痕迹。
    - 把结果写到 draft_meta.title / draft_meta.caption，沿用原始事实边界。
    - draft_meta 必须 generator=image_evidence_pack，记录 selectedAssetIds、citedSourcePaths、creativePlan（至少 2 个 concepts + selectedPlanId + selectionReason）和 selfCritique（readerPromise/titlePromise/informationDensity/evidenceBoundary/personaBoundary）。
  </always>
  <never>
    - 不要新增、替换或跨来源混图；不要改图、改来源或拼接多底稿。
    - 不得把 asset caption、实体名或来源信息重新拼成新标题/新配文。
    - 不得写 draft.article.md、长文、figure 块、二级标题、来源说明、自检表格或虚假亲历。
    - 完成后不要运行批次发布。
  </never>
</constraints>

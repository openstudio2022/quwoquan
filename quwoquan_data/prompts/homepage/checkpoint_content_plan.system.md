{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 为 activeCoverageTargets 完成证据驱动 content_plan；abandoned 对象不得再规划、注册或写 brief。
    - 底稿中心 1:1：枚举每个 coverageTarget 下所有合格 source unit，每个合格底稿各成一篇/一作品；篇数由合格底稿数决定，不再要求满足固定 entityArticlesPerTarget/imageWorksPerTarget 篇数，也不再要求 writingIntent 角度覆盖（writingIntent 是底稿派生的可选标签）。
    - 图片不足不应阻断合格实体，已选图片必须逐资产权利清晰合规。若现有 content_plan_packet 与规则冲突，直接重写。
    - 类型按底稿形态路由：实体主页主底稿来自 Wiki/百科/知识图谱/官网等实体介绍源，政府/文旅/媒体只作 supporting evidence；文章底稿来自 article_research，UGC、社区、媒体、官方和垂类专业文章同等按质量、事实密度、文字完整度和权利风险筛选。
    - 源图是加分与可选证据，article 必须写 baseSourceRef 且一稿一用，若使用 assetRefs 则资产必须权利合规（图文同源底稿，图片可跨内容复用，无需全批独占），无合格源图的优质文字底稿可写 publishMediaMode=text_only。
    - 图片作品底稿是 image_research 的图片集合，carrier=image，只写 sourceCollectionId/assetRefs，同一作品只能使用同一作者/页面/专辑/授权凭证下 1..20 张图，标题<=80字且可空，配文<=300字且可空。
    - 每个 article/image/video 内容对象必须绑定平台 creator assignment，字段至少包含 authorId、creatorProfileId、creatorArchetype、creatorProfileVersion、creatorDisclosure、experienceClaimMode、authorQualitySignals；creator 必须来自系统 creator registry。
    - 写 _shared/content_plan_packet.json（schemaVersion=quwoquan_data.content_plan_packet），注册 content_object，并写每项 3.compose/brief.json。
    - ref/title 必须由证据归纳；evidenceRefs 必须存在，blocked/reject 来源不可引用。
    - 完成后运行 content_plan validator 并修复到无问题。
  </always>
  <never>
    - 不得沿用旧 2+2/角度配额示例。
    - 文章只能引用 article_research；图片只能引用 image_research；homepage 来源不得拿来当文章/图片底稿。
    - 同一 baseSourceRef 在整个批次只能被一篇文章使用，严禁输出 baseSourceReusePolicy 或 multi_intent_source_bundle；如果可用 article base 不足，必须停留在 content_plan 修复，不能复用底稿凑数。
    - creator 不得由 author 临时发明，不得把 sourceUnit 图片/网页作者当作平台发布 author。
  </never>
</constraints>

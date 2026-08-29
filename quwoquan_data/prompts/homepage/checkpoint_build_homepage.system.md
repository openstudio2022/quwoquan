{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 读取 4.draft/prompt.md、3.compose/entity_page_input.json 与已下载 source.md/source.clean.md、主页模板，以底稿（primaryEvidenceRef）为唯一事实来源做事实校正+PII/平台痕迹清理+人设/体裁适配，把正文写回 4.draft/page.md（覆盖占位，去空白≥350字）。
    - 底稿沿用尺度只认 4.draft/prompt.md 里 `sourceUseMode` 那一条指令：`licensed_adaptation` 允许以底稿为骨架轻改，`factual_reference_only` 必须先抽事实再用自己的话重写并压缩体量。两者不可互换，本文件不再另给改写比例。
    - 写作前先从 3.compose/entity_page_input.json 的 `payload.baseDraft.sectionOutline` 建立标题清单；清单中的每个标题必须以相同文字和相同 `##`/`###` 层级原样写回，再在对应标题下写正文。
    - 当章节均衡未过时，保留原有必需 `##` 标题，并在其下拆出语义准确的 `###` 子章节；事实不得丢失，也不得靠大幅删文绕过章节占比门。
    - 不要逐句同义改写：先按事实顺序重组句式，再清理平台痕迹、隐私、病句、重复和时间线。
    - 失败提示沿用过多时，把长串原文换成自己的句式与语序并按信息价值取舍细节；提示脱离底稿时回到底稿事实重新起稿，禁止在旧成稿上继续扩写。
    - 若来源目录存在 source.judge.request.json（灰区来源判别请求），先按请求做门户/实体主页语义判别，把结构化 verdict 写回同目录 source.judge.json 再继续。
    - 若发现底稿讲的不是该实体本体（门户/列表/上级行政区/其它实体），按 prompt.md 失败协议在 4.draft/ 写 failure.json，不要硬写正文。
    - 完成后仅返回写回结果；只允许运行任务区指定的 homepage-draft 只读自检，不得运行其它 validator 或恢复 workflow。
  </always>
  <never>
    - 不得脱离底稿从零另写，也不得整篇零加工照搬，不得机械模板凑字。
    - 不得把「底稿」「sourceUseMode」「prompt.md」「source.md」「4.draft」等生产过程称谓写进正文；需要交代出处时直接陈述事实或点名可公开查证的来源，不写「底稿所载……」。
    - 除 `4.draft/page.md` 外，不要手写最终 `page.md`、asset://、_entity.json 或 manifest.json；父控制器 finalize 会据正文与已授权真实图自动补齐配图与三件套。
  </never>
</constraints>

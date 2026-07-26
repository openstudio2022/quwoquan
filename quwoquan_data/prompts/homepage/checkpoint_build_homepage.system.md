{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 读取 4.draft/prompt.md、3.compose/entity_page_input.json 与已下载 source.md/source.clean.md、主页模板，在底稿（primaryEvidenceRef）基础上做适度润色+事实校正+PII/平台痕迹清理+人设/体裁适配，把正文写回 4.draft/page.md（覆盖占位，去空白≥350字）。
    - licensed_adaptation 与 factual_reference_only 同等以底稿为骨架轻改：保留底稿信息顺序、关键事实和必需标题；首稿主动改写约 20%-30% 的句子，尤其不得连续逐句照搬。
    - 写作前先从 3.compose/entity_page_input.json 的 `payload.baseDraft.sectionOutline` 建立标题清单；清单中的每个标题必须以相同文字和相同 `##`/`###` 层级原样写回，再在对应标题下轻改正文。
    - 当章节均衡与底稿保真同时未过时，保留原有必需 `##` 标题，并在其下拆出语义准确的 `###` 子章节；保留底稿事实与多数原句，不得靠大幅删文绕过章节占比门。
    - 不要逐句同义改写：先按事实顺序重组句式，再清理平台痕迹、隐私、病句、重复和时间线；底稿留存率必须落在提示词声明的质量边界内。
    - 修复底稿留存率过低时，从底稿恢复事实顺序和多数原句骨架，只改写必要的约四分之一句子；禁止从旧成稿继续扩写，也禁止整篇退回原文。
    - 修复底稿留存率过高时，保持全部事实、标题和图片占位不变，分散改写约五分之一句子；禁止只换标点、繁简字或同义词。两类修复都以 65%-85% 为目标，避免在上下边界之间摆动。
    - 若来源目录存在 source.judge.request.json（灰区来源判别请求），先按请求做门户/实体主页语义判别，把结构化 verdict 写回同目录 source.judge.json 再继续。
    - 若发现底稿讲的不是该实体本体（门户/列表/上级行政区/其它实体），按 prompt.md 失败协议在 4.draft/ 写 failure.json，不要硬写正文。
    - 完成后仅返回写回结果；只允许运行任务区指定的 homepage-draft 只读自检，不得运行其它 validator 或恢复 workflow。
  </always>
  <never>
    - 不得脱离底稿从零另写，也不得整篇零加工照搬，不得机械模板凑字。
    - 除 `4.draft/page.md` 外，不要手写最终 `page.md`、asset://、_entity.json 或 manifest.json；父控制器 finalize 会据正文与已授权真实图自动补齐配图与三件套。
  </never>
</constraints>

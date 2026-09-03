<output_format>
- 把创作的正文写回同目录 `draft.article.md`（覆盖占位）。
- 正文用 Markdown：首行 `# 标题`；正文用自然的 `## ` 小标题分节；图按 `<figure_contract>` 原样保留占位符 fence。
- 在同目录 `draft_meta.json` 写：`generator=agent`、`model`、`styleFamily`、`openingStrategy`、
  `citedSourcePaths`、`coveredFacts`、`creativePlan`（≥2 候选构思 + selectedPlanId + selectionReason +
  readerPromise + unusedFacts）、`selfCritique`（readerPromise / titlePromise / informationDensity /
  evidenceBoundary / personaBoundary）。
- 写回后按当前 `4.draft` stage contract 补齐并自检 draft meta、author self-check 与 agent result envelope，
  运行其中点名的 verifier，再由宿主 AI 用真实结果显式执行 `task stage-close`；不得调用任何
  旧式组合审稿入口，也不得假定 review 自动运行、自动批准。
</output_format>

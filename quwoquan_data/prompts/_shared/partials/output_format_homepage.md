<output_format>
- 把创作的正文写回同目录 `page.md`（覆盖占位），正文去空白 ≥ {{min_page_chars}} 字，
  且每个 `##` 章节（不含『相关图片』）去空白 ≥ {{min_section_chars}} 字：
  写不够这个体量的章节直接省略或并入邻近章节，不要留下信息量不足的空壳小标题。
- 正文写**带多级小标题（`##`/`###`）的纯文字 Markdown**；底稿材料中形如 `[[IMG:fig_NN]]`
  的整行是系统图片占位符，必须原样带回（不改 id、不移动、不复制、不删除、不新增，行尾不加文字）。
- 当前 draft 阶段只写正文与阶段契约要求的过程产物；不得在正文中书写 `asset://`、`:::figure`、
  `:::gallery`、frontmatter、『相关图片』、`_entity.json` 或 `manifest.json`。
- 正文必须能在底稿 / 来源中回溯事实，禁止机械模板句、工程化口径与重复凑字。
- 写回后按当前 `4.draft` stage contract 自检正文、元数据、self-check 与 agent result envelope，
  运行其中点名的 verifier，并由宿主 AI 用真实结果显式执行 `task stage-close`；后继评审和 publish 也必须由宿主按 Skill 显式推进。
</output_format>

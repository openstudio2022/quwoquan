# data-legal · content-production · base

## PRE 准入

- [MUST] 每个待发布素材都有来源记录与授权快照
  check: 存在无来源记录的素材，判失败——不可追溯即不可发布
- [MUST] 已核对 blocked 来源列表
  check: 未核对，判失败

## DURING 执行中

- [MUST NOT] 发布不可商用素材或带平台水印的素材
  gate: python3 quwoquan_data/scripts/cli.py verify publish-purity
- [MUST NOT] 未经改写复现长句
  check: 抽查正文长句与来源原文比对；存在连续原文片段，判失败
- [MUST NOT] 使用无肖像依据的人物图片
  check: 逐张核对含人物的图片是否有肖像授权记录；缺记录即判失败
- [MUST NOT] 把官方来源的文案改写进正文、简介或 `keyFacts`；官方来源只允许用于
  `lanePolicies.homepage.structuredFactsPolicy.fields` 列出的结构化事实字段
  check: 对 `sourceClass=official` 的来源，检查其内容只出现在该 policy 列出的字段；
  出现在正文、简介或 `keyFacts`，判失败

## POST 自检

- [MUST] 发布纯度通过
  gate: python3 quwoquan_data/scripts/cli.py verify publish-purity
- [MUST] 发布生命周期通过
  gate: python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>
- [MUST] 每条结构化事实都有完整 `factSources`（`sourceId`、`sourceClass`、抓取 URL、
  观测时间、置信度）
  check: 缺任一项的字段必须不发布；已发布则判失败
- [SHOULD] 官方与百科冲突处已保留冲突记录而非静默取其一

## HANDOFF 交接

- 产出：授权快照清单、blocked 来源核对结果、冲突记录
- 未决项去向：权利存疑的素材直接排除出本次 release，并转 `OPEN-###` 记录原因
- 下一步：环境导入，由 environment-ops 工作流承接
- 证据链：上述 gate 输出与发布账本

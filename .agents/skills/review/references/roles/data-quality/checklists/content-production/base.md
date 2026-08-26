# data-quality · content-production · base

## PRE 准入

- [MUST] 内容已走完 `0.plan -> sources -> 1.download -> 2.quality -> 3.compose ->
  4.draft -> 5.review -> publish -> ship -> service importer` 链路，
  不停在离线文件层
  check: 只产出了离线文件就宣称完成，判失败
- [MUST] 正文由 Agent 基于 `writing_pack.json` 与 `prompt.md` 创作并写回，
  `generator=agent`
  check: 正文由脚本拼装，判失败

## DURING 执行中

- [MUST NOT] 用拍脑袋补全替代证据链
  check: 每条结构化事实必须能追到 `factSources`；无来源的补全，判失败
- [MUST NOT] 出现百科罗列、机械收尾、模板化小标题、来源痕迹、平台水印、
  未经改写长句复现
  check: 通读正文；命中任一项即判失败并指出具体段落
- [MUST NOT] 内容角度、实体类型、`tagRefs`、manifest、asset id、source paths、
  发布账本互相不一致；不一致先修契约或数据，不用代码绕过
  gate: make verify-data-release-consistency RELEASE_FILE=<release json 路径>
- [MUST NOT] 把 contract fixture、测试 seed 或基础设施探针投影到 feed/homepage/profile
  gate: make verify-app-mock-isolation

## POST 自检

- [MUST] Data 静态门通过
  gate: python3 quwoquan_data/scripts/cli.py verify all
- [MUST] Data 仓库门通过
  gate: make verify-quwoquan-data
- [MUST] 发布一致性成立
  gate: make verify-data-release-consistency RELEASE_FILE=<release json 路径>
- [MUST] 三层测试证据齐备：`local_contract` schema/静态/CLI/模块、
  `api_integration` importer/真实存储或环境采样、`user_acceptance` 用户消费链路
  gate: make verify-test-coverage-map
- [SHOULD] 数据管控字面量合规
  gate: make verify-data-control-literals

## HANDOFF 交接

- 产出：`releaseId`、import receipt、各 stage result 与 gate report 路径
- 未决项去向：证据不足的条目退回对应 stage（先判证据、再判 prompt/template
  失配、最后才判创作执行），不要在评审时硬修
- 下一步：环境导入，由 environment-ops 工作流承接
- 证据链：上述 gate 输出

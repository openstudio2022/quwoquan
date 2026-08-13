---
name: /plan-review
id: plan-review
category: Planning
description: 开发前从八角色审核当前会话计划与规格父链，并挂接五类工程自检维度
---

# /plan-review

目标：开发前从产品、UX、架构、代码、测试、用户、运维、运营八角色审核当前会话计划与规格父链；不写实现。

逐角色检查：独立用户价值与范围；Journey/父子责任；owner/DDD/metadata 单轨；主路径/边界/失败/并发；页面四态与平台体验；三层测试；SLO/告警/灰度/回滚；自动门禁与变更归属。

在八角色检查中显式核对五类自检维度（每条指向规则真相源，不复制清单）：

- **可测试性**（测试角色）：每条验收锚点可被三层测试直接绑定；被测决策可经导出 API 或对象级 typed double 观察，不依赖未导出符号旁路、test-only 后门或 fixture 注入（真相源：`runtime-test-pyramid` spec 与根 `AGENTS.md` 三层测试门）。
- **读写分离**（架构角色）：command/query 分流裁决明确；页面与 Provider 只依赖对象级 `*CommandWriter/*Query` typed port，禁止聚合 Repository 与运行时数据源切换（真相源：`.cursor/rules/08-mock-data-isolation.mdc`、`/extend` Command/Query 分流）。
- **领域模型与服务规范**（架构/代码角色）：对象边界完成 `owned_entity` vs `separate_aggregate` 裁决；DDD 依赖方向 `adapters/inbound → application → domain`，infrastructure 只实现 port；跨对象只依赖对方 domain/application port 或事件（真相源：`/extend` 对象边界检查、`quwoquan_service/AGENTS.md`）。
- **运维运营**（运维/运营角色）：SLI/SLO、指标与告警、配置来源、灰度与回滚已声明；环境证据入口统一 `stackctl`，不手写第二套 URL/拓扑（真相源：根 `AGENTS.md` 可观测与配置门、`quwoquan_ops/AGENTS.md`）。
- **前端规范**（UX/代码角色）：计划触及 App 时核对设计系统 token、i18n/UITextConstants、响应式断点、iOS 语义与页面四态是否在计划内（真相源：`.cursor/rules/02-dart-coding.mdc`、`09-page-horizontal-quality.mdc`、`07-ios-native-ux.mdc`）。

不符合项只能：当前增量补入对应 spec/design/metadata/测试计划；作为最低 owner 节点 OPEN；或明确 Out of Scope。禁止创建任务清单、changelog、成熟度矩阵或中央风险台账。

输出 `满足 / 待补 / 阻断`，每项指向具体 REQ/GWT/SIT/DOM/UAT/DEC/OPEN 或当前会话任务。通过后进入 `/baseline`、`/extend` 或 `/dev`；方案分叉退回 `/prd` + `/design`。

自然语言等价触发："开发前评审""规划是否完整""多角色看遗漏"。

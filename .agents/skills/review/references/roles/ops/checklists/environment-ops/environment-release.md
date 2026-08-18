# ops · environment-ops · base

适用：交付件是环境动作（发布、放量、回滚、修复）。
命令与拓扑细节见 [environment-ops](../../../../../../environment-ops/SKILL.md)，此处只做准出判定。

## POST 自检：release candidate 准出

- [MUST] UAT/SIT/GWT/contract 已闭环，且 api_integration 与 user_acceptance 有真实证据
  check: 以静态声明或历史报告替代本次执行，判失败
- [MUST] SLO 达标、灰度 step 与回滚版本明确、回滚演练已完成
  check: 回滚路径不清或未演练，判失败
- [MUST] 生产包默认 Remote，无 mock 切换入口
  gate: make verify-production-wiring-purity
- [MUST] 证据经 `stackctl` 产生：`verify --kind all`、`health --scope full`、`inspect`
  check: 手工拼装的环境证据不计
- [MUST NOT] 在缺 `prod-hosted` 人工确认时执行放量或破坏性 repair
  check: 放量或 repair 记录中找不到对应的人工确认，判失败
- [ADVISORY] `releaseEligibility` 与 `containerDeployment` 是两个独立结论：
  后者 passed 不代表前者可放量。

## HANDOFF 交接

- 产出：SLO、灰度 step、回滚版本、失败阈值与人工确认状态
- 未决项去向：未通过项转 `OPEN-###` 并标注准出影响
- 下一步：放量推进或回滚，由 environment-ops 工作流承接
- 证据链：`stackctl` 输出原文

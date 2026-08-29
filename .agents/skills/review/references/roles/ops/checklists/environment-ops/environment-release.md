# ops · environment-ops

- [MUST] candidate、环境、运行尝试与回执绑定同一不可变身份。
  check: 对照 candidate/attempt/receipt digest；任一身份不同或缺失时判失败。
- [MUST] 激活、health、readback、回滚与 replay 证据均为本次产生。
  evidence: environment-release-evidence
- [MUST] required evidence 失败立即阻断，不继续消耗 Reviewer。
  check: 读取 plan terminal 与调用记录；判失败后仍派 Reviewer 时判失败。
- [MUST NOT] 静态、历史或其他环境证据冒充目标环境准出。
  check: 对照证据环境/时间/attempt；任一不匹配时判失败。

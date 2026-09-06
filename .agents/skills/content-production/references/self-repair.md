# AI 自检与修正

在 CLOSE 前，宿主 AI 可根据当前阶段机械 verifier facts 与 AI self-check 修正本阶段尚未关闭的对象级业务产物：

```text
运行一条 verifier -> 读取真实 issue -> AI 对照语义目标自检 -> 定位本阶段结果 -> AI 修正 -> 重跑该 verifier
```

- 每次修正必须对应具体 issue，且不得改变 OPEN 冻结输入。
- verifier 失败指向前序输入缺口时，本阶段提交 `blocked` 与 typed issue，不跨阶段改写。
- 不得改 schema、verifier、阈值、allowlist、receipt、来源原始字节、权利证明或 review 事实来换取通过。
- CLOSE create-once 后不得再修；任何新尝试使用新 execution。
- 修正轮次由 AI 如实记录在本阶段业务结果中，仅供审计，不触发代码自动重试、恢复或仓内调度。
- `release` CLOSE 后 producer 已结束；环境侧失败不得触发 producer 原地修正，只能由下游 owner处理，或在确需新内容输入时显式发起新 execution。

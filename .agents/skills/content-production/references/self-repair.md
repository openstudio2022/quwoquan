# AI 自检与修正

在 CLOSE 前，宿主 AI 可根据当前阶段显式 verifier facts 修正本阶段尚未关闭的业务产物：

```text
运行一条 verifier -> 读取真实 issue -> 定位本阶段结果 -> AI 修正 -> 重跑该 verifier
```

- 每次修正必须对应具体 issue，且不得改变 OPEN 冻结输入。
- verifier 失败指向前序输入缺口时，本阶段提交 `blocked` 与 typed issue，不跨阶段改写。
- 不得改 schema、verifier、阈值、allowlist、receipt、来源原始字节、权利证明或 review 事实来换取通过。
- CLOSE create-once 后不得再修；任何新尝试使用新 execution。
- 修正轮次由 AI 在结果中如实记录，仅供审计，不触发代码自动重试或恢复。

# 分级、判据与输出

| 标签 | Board 裁决 | 使用条件 |
|---|---|---|
| `[MUST]` / `[MUST NOT]` | `GATE_BLOCK` | 必须紧跟 `evidence:` 或客观 `check:` |
| `[SHOULD]` / `[SHOULD NOT]` | `PR_WARN` | 需主会话显式裁决 |
| `[MAY]` / `[ADVISORY]` | 提示 | 不影响准出 |

`evidence: <id>` 只能引用 `registry.yaml` 的命名证据。Board 在派发前执行并去重，
Reviewer 只读结果，禁止自行补跑命令。`check:` 必须写清读取对象和失败谓词；“检查是否合理”
之类主观描述不构成判据。角色 checklist 不保存 `gate:` 命令。

Reviewer 每条 finding 固定为：

```text
[GATE_BLOCK] architect/design#2 — 页面绕过 typed port
  依据: <canonical context path#anchor>
  证据: <file:line 或 named evidence id + result>
  修复: <唯一可执行动作>
```

拿不出 canonical 依据与具体证据的结论不得提交。Reviewer 不执行修复、不扩大 scope、不启动
子代理；发现输入缺失时按 executor 契约返回 incomplete。

Board 汇总规则：

- evidence、Reviewer、取消与 stale 状态的等级和恢复动作只读取
  `quwoquan_ops/policies/agent_governance_contract.yaml#terminal_codes`，本文件不复制映射。
- findings 冲突时原样并列，主会话裁决，不由 Board 发明第三种结论。

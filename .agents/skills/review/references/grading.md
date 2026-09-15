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

## 主会话接纳规则

评审是建议与证据输入，不是实现授权。主会话回到交付负责角色，逐项检查：

1. **有效性**：canonical 依据、当前字节定位、失败路径或命名 evidence 齐全；仅风格偏好、推测或陈旧证据不构成必须修改项。
2. **适用性**：属于本 candidate 与 owner，未被现有实现覆盖、未与另一 finding 重复；范围外问题交最低 owner，不夹带扩大改动。
3. **收益与代价**：按用户影响、失效概率、维护风险及修复/回归成本排序；优先最小可验证修复，不为理论完美引入框架或全仓重构。确定性 blocker 必须修复或修正规则并重新取证，不能因成本高而豁免。
4. **裁决**：accepted（实现并复验）、rejected（给出反证/不适用依据）、duplicate（关联原项）、deferred（绑定有效 owner OPEN 与关闭条件）。这些是主会话解释标签，不新增机器 terminal；健康 finding 仍必须满足 canonical disposition 契约，不能用 rejected/deferred 标签绕过。
5. **角色回交**：接纳清单明确 finding、理由、最小修复范围及验证后，切回 dev/design/prd 执行。未接纳项不改代码；复验只覆盖修复点和受影响边界。无新证据不重审，同一分歧再现即交人类裁决，不追加角色、投票或递归评审。

输出保持紧凑：每项一条裁决及证据引用；证据相同不重复解释，预算沿用 registry，禁止另造审查轮数或中央接纳台账。

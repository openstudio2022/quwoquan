# /deploy

目标：发布 release batch / CR 范围。

准入：
- UAT/SIT/GWT/contract 已闭环。
- T3/T4、SLO、观测、灰度、回滚演练完成。
- 生产包默认 Remote，无 mock 切换入口。

阻断：SLO 未达、回滚不清、生产数据或 seed 边界不清。

执行：
1. 先按 `docs/agent_context_contract.md` 复核 release batch / CR 的规格、T1~T4、四环境、观测和回滚证据。
2. 对照 `docs/agent_command_simulation_matrix.md` 确认部署命令的禁止事项和出口证据。
3. 环境打包、验证、健康检查、巡检和部署统一使用 `python3 agent_ops/deploy/stackctl.py`。
4. 发布前至少执行或引用等价证据：

```bash
python3 agent_ops/deploy/stackctl.py verify --env <env> --kind all --tier all
python3 agent_ops/deploy/stackctl.py health --target <target> --scope full
python3 agent_ops/deploy/stackctl.py inspect --target <target> --kind all
```

5. `prod-hosted` 只通过 `stackctl deploy --target prod-hosted` 驱动 rollout stage；不存在 `prod-gray` 环境。

出口：
- 输出 stackctl verify/health/inspect/deploy 报告位置或等价证据。
- 输出 SLO、灰度 step、回滚版本、失败阈值和人工确认状态。
- 无 prod-hosted 人工确认时，不得执行放量或破坏性 repair。

自然语言等价触发：用户说“发布”“部署”“放量”“回滚”“检查环境能否上线”时，也按 `/deploy` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

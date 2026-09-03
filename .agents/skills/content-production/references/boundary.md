# Data 内容生产职责边界

| 主体 | 允许 | 禁止 |
| --- | --- | --- |
| 宿主 AI | 读上下文、显式选择 input refs 与来源、写业务产物、创作、自检、独立 review、决定 pass/blocked/typed issues、按 Skill 固定顺序推进、原生串并行 | 伪造证据、放宽 schema/verifier、手写 receipt、修改已冻结输入或 immutable release |
| Skill | 十阶段唯一业务说明、每阶段输入/输出、显式 verifier、固定后继与完成证据 | 复制 schema/代码常量、建立第二流程、registry、processor、模型/并发策略或状态机 |
| 代码内核 | `task init`、stage-open exact input freeze、stage-close create-once、下载/CAS、schema/硬事实 verify、单对象 publish、immutable release、ship 原子 IO | 来源/选材/创作/review、verdict/issue/next 派生、stage-gate registry、semantic wrapper、runner/fleet/claim、自动恢复、execution-state reducer |

硬约束：

1. 代码同步返回，不等待 AI 回写。
2. verifier 只验证可重复的硬事实，不作语义判断。
3. 每个 approved 对象独立原子 publish；一个对象失败不回滚其它已成功对象。
4. release 必须消费 AI 显式 cohort，禁止隐式 all-publishable。
5. ship 的 apply、readback/health 与 EAF 由 AI 显式调用和绑定。
6. receipt 与 immutable/environment facts 是跨会话唯一状态；无 shim、dual-read、legacy fallback 或 sequence-017 兼容。

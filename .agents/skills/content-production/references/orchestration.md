# 宿主执行方式

本文只说明宿主原生执行方式，不定义第二套流程。业务顺序、阶段输入输出与完成标准全部以 `SKILL.md` 和当前 stage contract 为准。

## 串行

一个宿主会话可按十阶段顺序执行一个 execution。每阶段完成 CLOSE 后再读取 Skill 的固定后继。会话中断时，下一会话只读 receipts 与业务产物接手。

## 并发

宿主具备原生子会话或任务能力时，可以并发处理不同 execution，或在 `5.review` 派发独立 reviewer 会话。每个会话只写自己负责的 execution/对象；共享 canonical、release 与 environment 只能经单对象或对应原子 IO 命令写入。

并发数量、模型选择、会话重启和任务排队属于宿主运行能力，不进入仓库业务契约、receipt、对象资格、release cohort 或 promotion。仓库中不得保存模型策略、fleet 状态、lane claim、worker identity、自动恢复或调度配置。

## 跨会话

跨会话唯一持久交接是：

- stage OPEN/CLOSE receipts；
- stage 业务 result refs；
- immutable release facts；
- environment append-only facts。

不得靠聊天摘要、后台进程、runner checkpoint、execution-state projection 或 campaign/fleet 状态恢复。OPEN 无 CLOSE时重做同一冻结阶段；CLOSE blocked 时新建 execution。

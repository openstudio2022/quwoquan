# 宿主执行方式

本文只说明宿主 runtime 如何执行 `SKILL.md` 定义的 producer 九阶段，不定义第二套流程、阶段或仓内状态。

## 串行

一个宿主会话可按九阶段顺序执行一个 execution。每阶段完成 CLOSE 后再读取 Skill 的固定后继；全部 release execution sequence-009/pass 后还必须 create-once 产出并复核 immutable terminal handoff，成功后才结束。会话中断时，下一会话只读 producer receipts 与业务 result refs 接手。

## 并发

宿主具备原生子会话或任务能力时，可以并发处理不同 execution。同一 execution 的 `4.draft` 全部对象必须由一个 author actor 会话负责，`5.review` 全部对象必须由另一个 reviewer actor 会话负责；不得在同一 stage 内按对象拆 actor，也不得建立 actor projection。共享 canonical 与 release 只能经对应单对象或显式 cohort 原子 I/O 命令写入。

并发数量、限流、模型选择、reviewer session 派发、会话重启和任务排队属于宿主 runtime，不进入仓库业务契约、receipt、对象资格、release cohort 或 milestone。仓库中不得保存模型策略、fleet 状态、lane claim、worker identity、自动恢复或调度配置。

下游 import/activate/readback、App/API UAT、EAF、sampling authority、promotion/rollback/replay 全部在本 producer workflow 范围外；如由其他 owner 独立消费 handoff，其调度与结果不得进入 handoff或写回 producer execution。

## 跨会话

producer 跨会话唯一持久交接是：

- stage OPEN/CLOSE receipts；
- stage 业务 result refs；
- immutable release handoff facts。

不得靠聊天摘要、后台进程、runner checkpoint、execution-state projection、campaign/fleet 状态或环境状态恢复 producer。OPEN 无 CLOSE 时重做同一冻结阶段；CLOSE blocked 时新建 execution；release CLOSE pass 时只读交接，不再写 producer stage。

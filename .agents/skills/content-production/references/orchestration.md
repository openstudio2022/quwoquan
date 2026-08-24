# 运行档位与模型策略

所有档位共用同一套阶段契约、receipt 协议、single-writer claim 与恢复判定；
档位只是「谁起会话、同时跑几条 lane」。**没有任何档位是某个宿主专属的**：
正式无人值守路径只有一份实现（`loop_driver.sh` + `fleet_dispatcher.sh`），
宿主命令经参数注入（Cursor `cursor-agent -p`、Codex `codex exec`、
Claude Code `claude -p`），换宿主 = 换 `HOST_CMD` 参数值，脚本与契约零改动。
驱动脚本内禁止任何 if-host 分支。

## single-writer claim（跨档通用协议）

- 一个 executionId 同时只有一个执行者。执行者启动先经 `task lane-claim`
  写 claim（`_shared/claims/lane.json`，含心跳时间戳，属可清理过程层，
  登记于 `core/paths.py`）；心跳过 TTL（默认 45 分钟）视为死 lane，可被安全接手。
- claim 的获取与释放只属于执行者（宿主会话）；驱动层（`loop_driver.sh`）
  只做 `task lane-claim --check` 只读预检，不写 claim——驱动抢 claim 会
  锁死自己派发的宿主会话。
- claim 冲突或 TTL 未过 → 不接手：另选 execution 或等待，不写任何产物。
- 执行者退出（完成/blocked/超轮）时经 `task lane-claim --release` 释放自己的
  claim（异主 no-op）；崩溃未释放的 claim 由 TTL 过期兜底。
- sources 复用池只读共享；lane 之间无共享可变状态。

## A 档：交互调试（M1 默认）

人在环。宿主 agent 按 [handoff-protocol.md](handoff-protocol.md) 逐阶段推进，
随时可停可查。宿主若有子会话能力（Task/subagent），可用它并行多条 lane 或派
独立 reviewer——这只是调试加速，claim/receipt/契约与其他档完全相同，每阶段
仍必须落 receipt，不得靠会话记忆跨阶段；无子会话能力的宿主串行做，无需任何
替代实现。

## B 档：ralph loop（无人值守单 execution）

外层驱动 `quwoquan_data/scripts/content/execution/runner/loop_driver.sh`
每轮起**全新会话**执行冻结 prompt（真相源 [loop-prompt.md](loop-prompt.md)）。
用法：`loop_driver.sh --execution-id <id> --host-cmd "<HOST_CMD>"
[--max-rounds 20] [--round-timeout 1800]`。

- 每轮只做一个阶段：上下文永远新鲜，磁盘即记忆。
- 驱动只读最新 receipt 的 `verdict` 与 `next` 决定续/停，不含业务判断。
- 终止条件：`next=END`、`verdict=blocked`、或达最大轮数（默认 20）。
- 单轮 hard timeout（默认 30 分钟）：超时杀会话进程，不写假 receipt；
  下一轮从 receipt 断点重来。
- 驱动不拼模型参数（`HOST_CMD` 自带 `--model auto` 等）；`5.review` 轮次的
  异族 judge 约束由该轮会话按 5.review 契约 PRE 执行（读 `4.draft` receipt
  指定异族），`verify rubric --generation-family` 门兜底。

## D 档：fleet（M10 → M100k，唯一正式并发实现）

`fleet_dispatcher.sh` 维持 N 个并行 `loop_driver` 进程（N 为显式并发上限参数），
每进程一个 executionId；backlog 是待办 executionId 列表文件，领取即写 claim。
**任何宿主的正式并发都走这里**（含 Cursor），不依赖 IDE 子会话工具。

- dispatcher 只做进程起/收/记录退出码，阶段语义零感知，向每条 lane 透传同一
  `HOST_CMD`。
- 规模化 = 水平复制 lane，不是纵向加编排；release 可按批次聚合多个 execution。
- 单 lane `blocked` 不传染：停该 lane 进人工/诊断队列，驱动层永不业务重试
  （宿主/API 瞬时错误例外：指数退避重启 ≤3 次，见 [boundary.md](boundary.md) 豁免）。
- 崩溃恢复零成本：重启 dispatcher 即可，receipt 链让任何 lane 从精确断点续跑。
- **汇合点串行**：`publish` / `release` / `ship` 每次只允许一条 lane 生效。
  互斥由 readiness 门 + 各原子命令自身的进程锁保证（canonical publish 根等
  共享真相源均有单进程锁），驱动层零感知；禁止任何旁路绕过原子命令写共享真相源。
  A 档人工调试同样只经原子命令进入汇合段，规则不变。
- 观测：`task fleet-status` 只读聚合 receipt 链，输出产出率、阶段分布、
  失败原因 TopN，对所有宿主同一格式；失败形态回流 `incident-inspection` 工作流。
- 分级晋升门：M1 → M10 → M100 → M1k → M10k → M100k，每级用真实运行数据标定
  （成功率、单内容成本、blocked 原因收敛）后才允许提并发上限，不允许跳级。
- 容量治理（DEC-028）：并发上限只来自 dispatcher 显式 `--max-parallel` 参数，
  标定证据只来自上一级 milestone 的 fleet 回执与 receipt 链；本轨不读取、
  不生成旧治理轨的 calibration receipt 或 execution policy 容量字段。

## 模型策略：主控与运行时分离

- **两层解耦**：IDE 主会话用什么模型与运行时无关。运行时模型由派发参数决定
  （`cursor-agent --model <m>`、SDK model 字段、子会话 model 参数），每轮可不同。
- **默认 auto**：所有阶段默认 `--model auto`，由宿主按任务自动路由；除非用户
  显式指定 gpt / claude 系模型，或命中下述强制规则。skill 不硬编码具体模型名。
- **每阶段画像（hint，不是锁定）**：
  - 机械阶段（`0.plan`、`1.download`、`publish`、`release`、`ship`：调 CLI + 验收）
    → auto 低成本路由。
  - 语义阶段（`sources` 研究、`2.quality` 判定、`3.compose`、`4.draft` 创作）
    → auto；质量不达标时可升格为显式指定强模型。
  - **`5.review` judge → 强制与 `4.draft` 实际生成模型不同族**。这是合规规则：
    派发前读 `4.draft` receipt 的 `actor.modelFamily`，显式指定异族模型；
    `verify rubric --generation-family` 门兜底。
- **可追溯**：每份 receipt `actor` 记录宿主、实际模型族、会话标识；
  `task fleet-status` 可按模型族切产出质量与成本分布，为 auto 路由提供标定数据。

## 评审独立性在各档位的实现

- 正式路径（B/D 档）不依赖子会话能力：`5.review` 天然单独占一轮全新会话，
  该轮注入 reviewer 人设 + 异族模型参数。
- A 档可派子会话注入 [roles/quality-reviewer.md](roles/quality-reviewer.md)
  / [roles/rights-reviewer.md](roles/rights-reviewer.md) 人设加速调试；
  无子会话宿主另起新会话，义务相同。
- 任何情况下 receipt `actor` 都必须记录会话与模型族。

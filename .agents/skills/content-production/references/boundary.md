# 三层职责边界（DEC-005）

真相源：[`runtime-data-engineering/design.md#dec-005`](../../../../specs/feature-tree/runtime/runtime-data-engineering/design.md#dec-005)。

## 三层分工

| 层 | 负责 | 禁止 |
| --- | --- | --- |
| 宿主 agent（执行主体） | 来源调研、正文创作、评审判断、流程推进决策、读校验报错自修产物、派发子会话/并发 lane | 手改 verify/schema、放宽门禁、伪造证据、手写 `execution_state.json` 或 receipt 文件 |
| Skill（契约文档） | 阶段序、每阶段产物位置/结构/文档要求、完成判据绑定、恢复与重试语义、自修轮次上限与升级出口、角色独立性 | 含任何代码逻辑；复制 schema/枚举/路径常量（第二真相源） |
| 脚本（检查 + IO） | verify 门禁、schema 校验、确定性下载/媒体 CAS、publish/release/ship 原子操作、preflight、receipt 原子记录 | 驱动或等待 agent、自动推进状态机、内置业务重试循环、生成正文 |

## 十条教训 → 设计规则

1. **单执行主体**（scale-005 `waiting_agent` 挂起）：脚本永不等待 agent；agent 同步调脚本、脚本同步返回，交接断点归零。
2. **补源循环**（scale-002/004 `RETAINED_SHORTFALL` 刚性停机）：sources 阶段内置合格判据 + 最大 3 轮扩策略检索；超限带缺口清单 `GATE_BLOCK`，不再一票 `manual_required`。
3. **自修契约**（scale-006 publish 盲试 3 次放弃）：verify 输出结构化 issue，agent 按 issue 修产物复验，每阶段 ≤3 轮，超限升级而非重试。见 [self-repair.md](self-repair.md)。
4. **skill 零代码**：新增代码只允许检查器与 IO 工具，单文件 ≤300 行。
5. **第二真相源禁令**：skill 只引用 `quwoquan_data/schema/**`、`quwoquan_data/scripts/core/stage_artifact_contract.py` 与 verify 命令；阶段名与磁盘目录名一字不差。
6. **渐进披露**：SKILL.md ≤150 行、每份契约 ≤200 行；agent 只按需读当前阶段契约。
7. **release 后缀同权**：publish 之后的 release/ship 与前段同等地位、同样有契约文件与验收命令；「成功」的定义包含环境导入回执。
8. **评审独立性**：`5.review` 必须由独立会话执行（有 subagent 能力的宿主派 subagent，无此能力的宿主起新 loop 轮次），author 会话不得自评；`verify rubric --generation-family` 的 judge≠generator 校验兜底。
9. **宿主无关**：skill 文本只依赖三种最低宿主能力——读文件、跑 shell 命令、（可选）派发子会话。规范真相源在 `.agents/skills/content-production/`。宿主入口只有两种合法形态：`.claude/skills` 是指向 `.agents/skills` 的 symlink（同一实体、零分叉；**对 `.claude/skills/**` 的任何写或删都会穿透到真相源本体，操作前必须先 `readlink` 确认**）；`.cursor/`、`.codex/` 放 ≤10 行指针 stub。禁止任何形态的全文镜像拷贝。
10. **磁盘即交接**：任何阶段的交接物全部落在工作包磁盘（产物 + stage receipt），不依赖会话上下文。任何宿主、任何新会话都能从 [recovery.md](recovery.md) 判定表 + receipt 链恢复到精确断点。
11. **容量治理不自建测量体系**（旧治理轨 calibration receipt 启动环）：宿主会话轨的并发上限只来自显式 fleet 参数，合法取值由上一级 milestone 的真实 fleet 回执标定（M1 → M10 → M100 → M1k 禁止跳级）；不读取、不生成 calibration receipt（设计归属 L2 `design.md#dec-028`）。

## 什么算编排代码（评审判据）

新增代码命中以下任一特征即越界，评审时 `GATE_BLOCK`：

1. 等待 agent（轮询 agent 状态、阻塞等 agent 回写）。
2. 自动推进状态机（代码决定「下一个业务阶段做什么」）。
3. 内置业务重试循环（对业务失败自动重跑）。

**唯一豁免**（阶段语义零感知的驱动层）：

- `loop_driver.sh` ≤50 行：只读最新 receipt 的 `verdict` 决定「再起一轮全新会话」或「停」。
- `fleet_dispatcher.sh` ≤100 行：只做进程起/收/记录退出码；宿主/API 瞬时错误可指数退避重启会话 ≤3 次——这是基础设施重试，不是业务重试。

二者不含业务判断、不解析 receipt 的业务字段、不等待 agent 中间态。

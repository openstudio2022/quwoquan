# 阶段交接协议

阶段间交接的唯一协议。工作包级主线共 10 个阶段（名字与磁盘目录一字不差）：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship
```

每阶段的实例化契约见 [stage-contracts/](stage-contracts/)。

## 四段生命周期（每个阶段统一执行序）

对齐根 `AGENTS.md` 五段执行契约：

1. **做前（PRE）**：读本阶段契约 → 验前置阶段 receipt 存在且 `verdict=pass` →
   复跑前置阶段完成判据命令确认磁盘事实。不信任 receipt 自述，防跨会话漂移。
2. **做中（DURING）**：契约 MUST/MUST NOT 持续生效；只写本阶段输出目录；
   验收失败进自修循环（≤3 轮，见 [self-repair.md](self-repair.md)）。
3. **做后（POST）**：跑本阶段完成判据命令（退出码 0）→ 调 `task stage-record`
   落 receipt。agent 不手写 receipt 文件，保证格式与写入权单轨。
4. **交接（HANDOFF）**：receipt 即交接物。四个交接字段对齐仓库 HANDOFF 契约：
   - `artifacts`：本阶段产出物的工作包相对路径清单。
   - `openItems`：未决项及去向，每项必须落到 `return_to_stage` /
     `gate_block` / `out_of_scope` 三者之一，不允许悬空。
   - `next`：唯一合法下游阶段（终态为 `END`；blocked 时指恢复重入阶段）。
   - `evidence`：判据命令与退出码、issue 数、自修轮数。

## Receipt

- schema 真相源：`quwoquan_data/schema/execution/stage_receipt.schema.json`
  （字段含 `executionId`、`stage`、`sequence`、`verdict=pass|blocked`、
  `actor{host,modelFamily,sessionId}`、四个交接字段、`recordedAt`）。
- 存放位置：`.qwq_output/data/tasks/<executionId>/_shared/receipts/`，
  文件名 `<sequence 3 位>-<stage>.json`，create-once 原子写（tmp+rename），
  已登记为 `_shared` 权威条目（`core/paths.py`），不可改写、不可删除。
- 记录命令（唯一写入口）：

```bash
python3 quwoquan_data/scripts/cli.py task stage-record \
  --execution-id <id> --stage <stage> --verdict pass|blocked \
  --actor-host <cursor|codex> \
  --actor-model-family <族名，auto 路由时记实际族> \
  --actor-session <会话标识> \
  --artifact <相对路径> [--artifact ...] \
  --next <stage|END> \
  --evidence-command "<命令>::<退出码>" [--evidence-command ...] \
  --issue-count <N> --repair-rounds <0..3> \
  [--open-item "<描述>::<return_to_stage|gate_block|out_of_scope>[::<returnStage>]"]
```

- `actor.modelFamily` 是评审独立性凭据：`4.draft` receipt 记录生成模型族，
  `5.review` 派发时读取它并指定异族 judge，`verify rubric --generation-family` 兜底。

## execution_state 合并方式（写入权移交，DEC-005）

- `_shared/execution_state.json` 是 receipt reducer 产生的只读最小投影；唯一写盘入口是
  `content.execution.receipt_state_reducer.reduce_receipt_projection`。`context.save_execution_state`
  永久拒绝业务写者；agent、skill 与其他命令一律不手写。
- `task stage-record` 先 create-once 写 receipt，再由全部 receipt 确定性重算 projection：
  - `stage=ship` 且 `verdict=pass` → `status=succeeded`（execution 终态的唯一合法来源）。
  - `verdict=blocked` → `status=manual_required`。
  - 其余 pass receipt → `status=running`。
- 终态（`succeeded`/`superseded`）受 layout/readiness 门保护，不可 resume；
  重试语义见 [recovery.md](recovery.md)。

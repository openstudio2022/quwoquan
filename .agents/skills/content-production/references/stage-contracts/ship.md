# 阶段契约：ship

把 immutable release 幂等导入目标环境并完成消费侧核验。execution `succeeded`
终态的唯一合法来源是本阶段 pass receipt。

## 身份

- stage：`ship`（与磁盘目录一字不差）
- 前置阶段：`release`
- 合法 next：`END`（终态）
- 角色人设：[release-operator](../roles/release-operator.md)
- 写目录 allowlist：`.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`
  （只经 ship 命令与核验流程）

## 做前（PRE）

- `release` receipt `verdict=pass`；复跑：

```bash
python3 quwoquan_data/scripts/cli.py verify release-integrity --release <releaseId>
python3 quwoquan_data/scripts/cli.py verify media-release-contract
```

- 目标环境健康：

```bash
python3 quwoquan_ops/cli/stackctl.py health --env gamma
```

- 涉及环境操作时同步加载 `quwoquan_ops/AGENTS.md`。

## 做中（DURING）

- 唯一 CLI：`python3 quwoquan_data/scripts/cli.py ship apply --env gamma …`
  幂等导入；回执、API 核验、回滚与重放证据写环境 run
  （`.qwq_output/env/gamma/runs/data-release/<releaseId>/<runId>/`）。
- App UAT：用真实 App 消费链路验证内容可发现、可搜索、可消费，证据入环境 run。
- [MUST NOT] 修改 canonical 或 release；[MUST NOT] 用 fixture、seed 或旧回执
  顶替本次导入证据。

## 做后（POST）

交付件：导入回执 + API 核验 + App UAT 证据。完成判据：

```bash
python3 quwoquan_data/scripts/cli.py verify release-lifecycle \
  --release <releaseId> --environment gamma --import-run <runId>
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile integration
```

常见 issue → 修复：

- 导入计数不等（Manifest/导入/active/Search/Recommendation） → 按 issue 定位
  断链环节重跑幂等导入，不手补投影。
- 环境不健康 → 走 `environment-ops` 工作流修环境，本阶段保持未完成。

### verify 失败重试 SOP

verify run 是 append-only 证据：失败的 run 目录原样保留，禁止改写或删除。
失败重入的固定操作序，逐条依次判断：

1. **换新 run-id 重跑 verify，不重导入**：`ship apply` 导入是幂等的且证据
   独立于 verify；只要 release、导入结果与环境 runtime 没变，重试只发生在
   verify 层。
2. **research isolation proof 自动复用**：runtime proof 效度域为
   `releaseId + manifestDigest + runtime 策略快照 + 24 小时时效`（DEC-034），
   不绑 verify run。同一 release 的后续 verify run 会自动发现并复用最近一次
   未超龄 PASS proof（重绑当前 run-id、`reusedFromVerifyRunId` 写明来源后
   落盘），无需重跑完整 probe。release 内容、导入或 runtime 策略变更，或
   proof 超过 24 小时时效时，必须重新执行
   `stackctl research-isolation-probe`。
3. **需要重导入的唯一情形**：release 本身变更（新 releaseId 或 manifest
   digest 漂移），此时从 `ship apply` 重新开始，旧 run 证据保留。
4. **环境卡点不在本阶段修**：`stackctl down` 对孤儿 compose 网络幂等回收；
   若 down/up 仍不收敛，走 `stackctl doctor` → `repair`（environment-ops），
   不得手工 `docker` 清理后继续本阶段。

按 [handoff-protocol.md](../handoff-protocol.md) 落 receipt；
`verdict=pass` 时 `task stage-record` 顺带置 `execution_state.status=succeeded`。

## 交接（HANDOFF）

- 终态 receipt：`next=END`。
- HANDOFF 报告用户或交 `plan-next`：release 与 UAT 证据路径、OPEN 变化、剩余阻断。

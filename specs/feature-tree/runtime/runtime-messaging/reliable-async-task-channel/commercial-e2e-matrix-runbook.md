# 群头像商用端到端全矩阵 — 执行手册（不打折扣）

本文档与 [`avatar-e2e-validation.md`](./avatar-e2e-validation.md) 口径一致：**在未具备 infra 且未产出四类环境非 dry-run、可追溯 JSON 证据前，不得声明「商用端到端全矩阵完成」。**

## 1. 商用声明定义（零折扣）

下列 **四条** 必须 **全部** 满足；缺一即为 **GATE_BLOCK**。

| 序号 | 环境 | 含义 | 证据形态 |
|------|------|------|----------|
| E1 | **beta** | 对接真实 beta 网关与 chat/media/user-sync；双端（Android + iOS）Patrol | `schemaVersion=1`、`status=passed`、非 dry-run、`environment.env=beta` |
| E2 | **local-gamma** | `start_local_gamma_mirror` + T3/T4 + Patrol；与镜像拓扑一致 | `environment.env=local-gamma`（或与脚本约定等价字段） |
| E3 | **cloud-gamma-pre** | ECS pre + API probe + self-hosted Patrol（chat-avatar matrix） | run id / artifact URL；probe + device JSON |
| E4 | **cloud-gamma-prod-smoke** | prod 变更后 smoke：probe + self-hosted Patrol | 同上，`environment` 标明 prod-smoke |

**共同约束**

- 每条证据：`scenario=chat.group_avatar.sync_display_e2e`（或与验收脚本约定），**禁止**仅用 `--dry-run synthetic device** 冒充商用矩阵。
- Android、iOS **各至少一台**真实模拟器或物理机（Patrol 可执行）。
- `serviceEndpointEvidence` / `serviceEvidence` 按 [`avatar-e2e-validation.md`](./avatar-e2e-validation.md) 最小字段集归档。

## 2. Infra 前置

在启动矩阵前确认：

- **GitHub**：`deploy-gamma-ecs.yml` / `app-env-device-matrix-self-hosted.yml` 所需 **secrets**（ECS SSH、测试 token 等）与 **vars**（`GAMMA_BASE_URL`、`MEDIA_AVATAR_CDN_BASE_URL`、`media_base_url` 传递链）。
- **Self-hosted runner**：带 Android SDK + Xcode/iOS 模拟器；workflow 中 `matrix_kind: chat-avatar` 与设备变量（如 `CHAT_AVATAR_MATRIX_ALL_DEVICES`）已配置。
- **ECS**：pre/prod 可达；与本手册 E3/E4 对齐。

本地自检（不替代云上证据；脚本 `warnings` 会提示 E3/E4 无法在离线会话核验）：

```bash
python3 agent_ops/avatar/check_avatar_commercial_matrix_prereqs.py --strict
```

## 3. 执行顺序（推荐）

1. **Phase L — local-gamma**（可先在无 ECS 情况下推进）：启动镜像 → healthz → `run_local_gamma_t3.py` / T4 → `run_local_gamma_avatar_e2e.py` → `run_chat_avatar_device_matrix.py`（无 `--dry-run`，双端）。
2. **Phase B — beta**：beta 网关与 seed/token 就绪 → `run_chat_avatar_e2e_probe.py` → Patrol（双端）。
3. **Phase C — cloud**：推送或 `workflow_dispatch` 触发预发/冒烟流水线；从 Actions artifact 下载 JSON，核对四条齐全。
4. **机器校验（必选）**：将四类报告路径写入 manifest（示例：[`artifacts/commercial-matrix/chat-avatar/manifest.sample.yaml`](../../../../../artifacts/commercial-matrix/chat-avatar/manifest.sample.yaml)），运行：
   ```bash
   COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml \
     make verify-chat-avatar-commercial-matrix
   ```
   或 `python3 agent_ops/avatar/verify_chat_avatar_commercial_matrix_evidence.py --manifest PATH`。退出码 **0** 才允许在 T9/本文档勾选「四条齐全」；**2** 表示 `GATE_BLOCK`（含 dry-run 混入、`status!=passed`、缺 Android/iOS 之一等）。
5. **归档**：将 manifest 路径、校验命令、CI `run_id` 写入 [`tasks.md`](./tasks.md) T9 与 [`avatar-e2e-validation.md`](./avatar-e2e-validation.md)「当前执行证据」。

### 3.1 一键编排（Phase L + 可选 Phase B）

仓库提供：

```bash
# 仅本机 Phase L：prereqs → 路由自检 → T3 → run_local_gamma_avatar_e2e（非 dry-run）
bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

# 先起 Docker 镜像栈
COMMERCIAL_MATRIX_START_MIRROR=1 bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

# 追加 beta（需 BETA_GATEWAY_BASE_URL + token）
BETA_GATEWAY_BASE_URL=http://127.0.0.1:18080 BETA_TEST_AUTH_TOKEN=... \
  bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

# 仅对已填 manifest 做校验（不跑 Patrol）
COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml \
  bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

# Makefile
make run-chat-avatar-commercial-matrix-local
```

E3/E4 探针与矩阵 JSON 由 [`deploy-gamma-ecs.yml`](../../../../../.github/workflows/deploy-gamma-ecs.yml) 与 self-hosted 作业产出；下载后放入 manifest 再执行校验。

## 4. 命令备忘（仓库根目录）

路径与参数以脚本 `--help` 为准；以下为典型形态。

```bash
# Local gamma：镜像（示例）
bash quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh

# Probe（非 dry-run 需可达 gateway）
python3 agent_ops/avatar/run_chat_avatar_e2e_probe.py --help

# T3（含 chat）
python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py

# Device 矩阵（商用必须去掉 dry-run，且具备双端设备）
python3 agent_ops/avatar/run_chat_avatar_device_matrix.py --help
python3 agent_ops/avatar/run_chat_avatar_device_matrix_ci.py --help
```

## 5. 声明检查清单（PR / 发布前）

- [ ] E1 beta：Android + iOS JSON，`status=passed`
- [ ] E2 local-gamma：同上（或 `aggregate` 报告内含 probe + deviceMatrix 均 `passed`）
- [ ] E3 cloud-gamma-pre：CI artifact 或等价可追溯路径
- [ ] E4 prod-smoke：同上
- [ ] `make verify-chat-avatar-commercial-matrix COMMERCIAL_MATRIX_MANIFEST=...` 退出码 0
- [ ] 文档：`avatar-e2e-validation.md` 与 `tasks.md` T9 与证据一致，无「已完成」与 GATE_BLOCK 矛盾表述

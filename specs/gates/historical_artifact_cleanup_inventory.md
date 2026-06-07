# 过往产物系统清理盘点

更新时间：2026-06-04

本文专门回答“仓库里的过往产物到底有哪些、哪些是当前状态、哪些只是过往证据、哪些必须迁移后才能删”的问题，并给出不做兼容层的清理任务列表。当前文档已同步到本轮结构性迁移完成后的状态。

## 清理原则

- 不做旧路径兼容，不保留“双写 / 双读 / fallback 到旧目录”的过渡逻辑。
- 先把仓库内文件分成 `状态`、`可重建快照`、`纯过往证据` 三层，再决定删法。
- 当前活跃环境的运行态目录不直接清；要么等停栈后删，要么先迁出新的状态根目录再删。
- 证据目录可以清，但要一次按批次清，不按单个日志挤牙膏。

## 一次性结论

当前仓库里的“过往产物”不是一类东西，而是四类混在一起：

1. `仓库内状态`
   - `.release-state`
   - `.control-plane-state`
   - `quwoquan_service/services/*/.runtime-cache`

2. `本地环境运行态`
   - `tmp/alpha_stack`
   - `tmp/beta_stack`
   - `tmp/app_beta_manual`
   - `tmp/app-instances`
   - `artifacts/local-gamma` 中被当前 mirror 直接挂载和读写的子树

3. `可重建快照`
   - `artifacts/app-env-packages`
   - `artifacts/service-env-packages`

4. `纯过往证据`
   - `artifacts/stackctl`
   - `artifacts/stackctl-audit`
   - `artifacts/device-matrix`
   - `artifacts/homepage-assets`
   - `artifacts/local-gamma/runs`
   - `tmp/` 下大量一次性运行报告、PR/CI 调试目录、纹理诊断日志

真正要清仓的主目标是第 4 类；真正要重构后才能彻底收口的是第 1、2 类。

## 目录全量盘点

### A. 仓库内状态

#### `.release-state`

用途：

- prod 灰度 / 自动发布的当前版本状态
- `stackctl`、workflow、platform-ops 都会直接读取

当前判断：

- 不是普通过往产物
- 是“把运行状态塞进仓库”的过往设计包袱

本轮已收口：

- 已迁到 `state/release/`
- workflow / stackctl / 发布脚本已切到新状态根

#### `.control-plane-state`

用途：

- platform-ops / product-ops 当前的文件型持久层

当前判断：

- 不是过往日志
- 是服务状态存储

本轮已收口：

- 已迁到 `state/control-plane/`
- 仓库根旧目录已退出默认读写链路

#### `.runtime-cache`

用途：

- config resolve 的磁盘 fallback snapshot

当前判断：

- 不是纯证据
- 是运行兜底

本轮已收口：

- 已迁到 `state/runtime-cache/`
- 不再散落在 service 子目录

### B. 本地环境运行态

#### `tmp/alpha_stack`

用途：

- alpha mock 栈 pid/pgid/log/report

当前判断：

- 只在 alpha 栈活着时必要
- 停栈后就是一次性运行态残留

#### `tmp/beta_stack`

用途：

- beta 本地栈 pid/pgid/log

当前判断：

- 只在 beta 栈活着时必要

#### `tmp/app_beta_manual`

用途：

- beta manual stack 的日志、process state、stack env、报告

当前判断：

- 不只是 log 目录，而是当前控制目录

#### `tmp/app-instances`

用途：

- app instance 注册表
- `start/stop/list_app_instance` 会读

当前判断：

- 这是运行态账本，不是普通 temp

#### `artifacts/local-gamma`

这里是最重的混合目录。

迁移前运行态必要子树：

- `artifacts/local-gamma/config-root`
- `artifacts/local-gamma/media`
- `artifacts/local-gamma/Caddyfile`
- `artifacts/local-gamma/model-cache`
- `artifacts/local-gamma/media-origin.pid`
- `artifacts/local-gamma/colima-tunnels.pids`
- `artifacts/local-gamma/stack_state.json`

纯过往 / 证据子树：

- `artifacts/local-gamma/runs`
- `artifacts/local-gamma/report.json`
- `artifacts/local-gamma/t3_report.json`
- `artifacts/local-gamma/t4_report.json`
- `artifacts/local-gamma/avatar_e2e_report.json`
- `artifacts/local-gamma/content-seed-report.json`
- `artifacts/local-gamma/*probe*.json`
- `artifacts/local-gamma/*.log`

当前判断：

- 同一目录同时承载运行态和过往证据，是当前最需要拆分的残留点

本轮已收口：

- 运行态已迁到 `state/local/gamma`
- `artifacts/local-gamma` 只保留证据文件
- 删除了运行态继续混放在 `artifacts/` 下的默认假设

### C. 可重建快照

#### `artifacts/app-env-packages`

用途：

- app 环境包快照
- gate / doctor / purity 校验会读

当前判断：

- 可重建
- 但当前工具链把它当成验证输入，不适合本轮直接清空

#### `artifacts/service-env-packages`

用途：

- service 环境包快照

当前判断：

- 同上

### D. 纯过往证据

#### `artifacts/stackctl`

用途：

- `package / up / down / health / inspect / doctor / deploy` 的按轮次报告树

当前判断：

- 纯过往证据
- 最适合按环境 / 目标 / 轮次做 retention

#### `artifacts/stackctl-audit`

用途：

- 专项 doctor / health / inspect 审计产物

当前判断：

- 纯过往证据

#### `artifacts/device-matrix`

用途：

- 设备矩阵、assistant、avatar、patrol 运行报告

当前判断：

- 纯过往证据

#### `artifacts/homepage-assets`

用途：

- homepage-assets scan / repair / delivery 报告

当前判断：

- 纯过往证据

#### `tmp/` 下纯过往一次性目录

当前已识别典型项：

- `tmp/runs/dry-run-ios`
- `tmp/assistant_beta_manual`
- `tmp/assistant_skill_comparison_logs`
- `tmp/assistant_device_matrix_logs`
- `tmp/ipad_weather_regression`
- `tmp/gh-run-*`
- `tmp/gh-pr*`
- `tmp/job-*.txt`
- `tmp/manual-gamma-readiness-report.json`
- `tmp/gamma-patrol-dry-run.json`
- `tmp/discovered_devices.json`
- `tmp/validate-mobile-devices.json`
- `tmp/pageflip_back_texture*.log`
- `tmp/assistant_beta_manual_e2e.log`

当前判断：

- 纯过往证据
- 不参与当前环境运行

## 代码与脚本依赖总览

### 当前强依赖 `state/local/gamma` + `artifacts/local-gamma`

- `quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`
- `quwoquan_service/docker-compose.gamma-local.yaml`
- `quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
- `agent_ops/deploy/stackctl.py`
- `agent_ops/deploy/gamma/deploy_gamma_ecs.sh`

### 当前强依赖 `state/local/app_beta_manual` / `state/app-instances`

- `quwoquan_app/scripts/device/start_app_beta_manual.sh`
- `quwoquan_app/scripts/device/stop_app_beta_manual.sh`
- `agent_ops/lib/beta_manual_lifecycle.sh`
- `quwoquan_app/scripts/device/start_app_instance.sh`
- `quwoquan_app/scripts/device/stop_app_instance.sh`
- `quwoquan_app/scripts/device/list_app_instances.sh`
- `agent_ops/deploy/stackctl.py`

### 当前强依赖 `state/release`

- `agent_ops/deploy/prod/config_release_gray_rollout.sh`
- `agent_ops/deploy/prod/config_release_rollback.sh`
- `agent_ops/deploy/stackctl.py`
- `.github/workflows/deploy-prod-auto.yml`
- `.github/workflows/deploy-prod-gray.yml`
- `quwoquan_service/services/platform-ops-service/cmd/api/main.go`

## 不做兼容的目标结构

目标不是“在旧目录旁边再挂一套新目录”，而是直接收口：

1. 仓库状态统一迁到 `state/`
   - `state/release/`
   - `state/control-plane/`
   - `state/runtime-cache/`
   - `state/local/alpha_stack`
   - `state/local/beta_stack`
   - `state/local/app_beta_manual`
   - `state/local/gamma`
   - `state/app-instances/`

2. `artifacts/` 只保留证据
   - `artifacts/stackctl/`
   - `artifacts/device-matrix/`
   - `artifacts/avatar-e2e/`
   - `artifacts/homepage-assets/`
   - 不再混入 pid、运行态 state、运行期 media cache

3. `tmp/` 只留进程级真正短时临时文件
   - 不再承载环境状态
   - 不再作为人工运行证据长期堆积

## 清理任务列表

### T1. 清空纯过往一次性 `tmp/` 产物

范围：

- `tmp/runs/dry-run-ios`
- `tmp/assistant_beta_manual`
- `tmp/assistant_skill_comparison_logs`
- `tmp/assistant_device_matrix_logs`
- `tmp/ipad_weather_regression`
- `tmp/gh-run-*`
- `tmp/gh-pr*`
- `tmp/job-*.txt`
- `tmp/manual-gamma-readiness-report.json`
- `tmp/gamma-patrol-dry-run.json`
- `tmp/discovered_devices.json`
- `tmp/validate-mobile-devices.json`
- `tmp/pageflip_back_texture*.log`
- `tmp/assistant_beta_manual_e2e.log`

执行性质：

- 可立即执行

### T2. 清空纯过往证据目录

范围：

- `artifacts/homepage-assets`
- `artifacts/stackctl-audit`
- `artifacts/device-matrix`

执行性质：

- 可立即执行

### T3. 清理 `artifacts/local-gamma/runs`

范围：

- `artifacts/local-gamma/runs/**`

执行性质：

- 可立即执行
- 但只删 `runs` 子树，不动 live runtime 子树

### T4. 收缩 `artifacts/stackctl` 过往报告

范围：

- `artifacts/stackctl/**`

执行结果：

- 已执行
- 当前策略为：每个环境/目标/命令分组仅保留最新一份时间戳报告；固定 contract 目录保留

### T5. 拆分 `artifacts/local-gamma`

动作：

- 迁出运行态子树到新的 `state/local/gamma`
- `artifacts/local-gamma` 仅保留报告/证据文件

执行结果：

- 已执行
- `start_local_gamma_mirror.sh`、`docker-compose.gamma-local.yaml`、`verify_local_gamma_mirror.py`、`deploy_gamma_ecs.sh` 已切到新路径

### T6. 迁移 `tmp/app_beta_manual`、`tmp/beta_stack`、`tmp/alpha_stack`、`tmp/app-instances`

动作：

- 统一迁到 `state/local/*` 和 `state/app-instances`

执行结果：

- 已执行
- 当前已统一迁到 `state/local/*` 与 `state/app-instances`

### T7. 迁移 `.release-state`、`.control-plane-state`、`.runtime-cache`

动作：

- 不再把状态存在仓库根或 service 目录
- workflow / stackctl / platform-ops 改为读新状态根

执行结果：

- 已执行
- 当前默认写入与读取均已迁到 `state/release`、`state/control-plane`、`state/runtime-cache`

## 本轮执行策略

本轮已按“不做兼容、直接切根”的原则完整执行 `T1~T7`。

## 本轮已执行结果

已执行并完成两层清理：

1. 第一层：纯过往证据清仓

   - `tmp/` 一次性过往目录 / 文件
   - `tmp/runs/dry-run-ios`
   - `tmp/assistant_beta_manual`
   - `tmp/assistant_skill_comparison_logs`
   - `tmp/assistant_device_matrix_logs`
   - `tmp/ipad_weather_regression`
   - `tmp/gh-run-25593386308`
   - `tmp/gh-pr11-gamma-readiness`
   - `tmp/manual-gamma-readiness-report.json`
   - `tmp/gamma-patrol-dry-run.json`
   - `tmp/discovered_devices.json`
   - `tmp/validate-mobile-devices.json`
   - `tmp/assistant_beta_manual_e2e.log`
   - `tmp/job-*.txt`
   - `tmp/pageflip_back_texture*.log`

   - `artifacts/` 纯过往证据目录
   - `artifacts/homepage-assets`
   - `artifacts/stackctl-audit`
   - `artifacts/device-matrix`

   - `local-gamma` 过往 run 证据
   - `artifacts/local-gamma/runs`

2. 第二层：结构性迁移收口

   - `tmp/alpha_stack` → `state/local/alpha_stack`
   - `tmp/beta_stack` → `state/local/beta_stack`
   - `tmp/app_beta_manual` → `state/local/app_beta_manual`
   - `tmp/app-instances` → `state/app-instances`
   - `.release-state` → `state/release`
   - `.control-plane-state` → `state/control-plane`
   - `quwoquan_service/services/product-ops-service/.runtime-cache` → `state/runtime-cache`
   - `artifacts/local-gamma` 运行态子树 → `state/local/gamma`
   - `artifacts/stackctl/**` 过往时间戳报告按分组收缩，仅保留最新一份

执行后验证：

- `stackctl health --target alpha-local` 通过
- `stackctl health --target beta-local` 通过
- `stackctl health --target gamma-local` 通过

结论：

- 当前活跃环境在迁移后保持可用
- 本轮已完成“纯过往证据清仓 + 状态根迁移 + local-gamma 运行态拆分 + stackctl retention 收缩”
- 后续若再清理，重点应转为过往文档/样例引用收口，而不是继续保留旧目录为默认入口

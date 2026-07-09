# 环境启动噪音统一清理清单

更新时间：2026-06-04

本文用于统一归档 `alpha-local`、`beta-local`、`gamma-local` 启动/运行期的雷同噪音问题，避免同类问题在不同环境重复返工。

## 已修并验证

### 1. Mock / 本地 gateway 缺少轻量只读接口

- `alpha-local`
  - 已补 `GET /v1/chat/inbox`
  - 已补 `GET /v1/chat/conversations`
  - 已补 `POST /v1/user/sync`
  - 已补 `POST /v1/ops/events`
  - 已补 `GET /v1/ops/events/summary`
  - 已补 `GET /v1/ops/events/drilldown`
  - 已补 `POST /v1/ops/visits`
  - 已补 `GET /v1/ops/visits/stats`
  - 已补 `GET|POST /v1/ops/experiments/*`

- `beta-local`
  - 已补 `GET /v1/app-messages/unread-count`
  - 已补 `GET /v1/notifications/unread-count`
  - 已补 `GET /v1/content/feed/intersections`
  - 已补 `GET /v1/content/intersections/summary`
  - 已补 `GET /v1/content/intersections`
  - 已补 `POST /v1/content/intersections/visit`
  - 已补 `POST /v1/content/intersections/exposure`
  - 已补 `GET /v1/app-messages/{messageId}`
  - 已补 `POST /v1/app-messages/{messageId}/ack`
  - 已补 `POST /v1/app-messages/{messageId}/read`

验证结果：

- `python3 quwoquan_ops/cli/stackctl.py health --target beta-local --scope full` 通过
- `python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope full` 通过
- beta 当前手动 smoke 已验证：
  - `/v1/app-messages/unread-count`
  - `/v1/notifications/unread-count`
  - `/v1/content/feed/intersections?limit=2&channel=recommend`

### 2. 日志追加导致过往 404/501 污染当前排查

- `alpha-local`
  - `quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh` 已改为启动时覆盖写日志

- `beta-local`
  - `quwoquan_ops/cli/beta/start_beta-local.sh` 已改为启动时覆盖写日志
- `quwoquan_ops/lib/beta_manual_lifecycle.sh` 已改为覆盖写 `.qwq_output/local/beta-local/*.log`

结论：

- 当前 `beta-local` 与 `beta-local` 的日志不再把旧故障持续追加到新运行轮次
- 后续排查可直接以最新轮次日志为准

### 3. beta fallback 依赖端口漂移

问题模式：

- beta 手动栈在 chat fallback 场景下依赖 local-gamma 的 Mongo/Redis
- 脚本仍使用旧默认端口 `37017/36379`
- 当前 canonical `gamma-local` 端口已迁到 `19410/19420`

已修：

- `quwoquan_app/scripts/device/start_beta-local.sh` 改为直接读取 `gamma-local` 端口 profile
- 不再保留过时默认端口

验证结果：

- beta 当前运行日志已出现：
  - `chat mongo fallback OK: mongodb://127.0.0.1:19410/?directConnection=true`
  - `chat redis fallback OK: 127.0.0.1:19420`
  - 后续 `chat-service`、`gateway`、notification unread-count、feed intersections 全部通过

### 4. 启动 smoke 面不足，导致缺口长期潜伏

已补：

- `quwoquan_app/scripts/device/start_beta-local.sh`
  - 新增 notification unread-count smoke
  - 新增 aggregate unread-count smoke
  - 新增 feed intersections smoke

- `quwoquan_ops/cli/stackctl.py`
  - `beta-local health` 新增：
    - `app-messages-unread-count`
    - `feed-intersections`

结论：

- 后续 beta 若再回退这些接口，`start_beta-local.sh` 与 `stackctl health beta-local` 会直接失败

### 5. beta 控制面启动噪音

问题模式：

- `platform-ops-service` 启动时读取 control-plane schema 的路径少了一层 `quwoquan_service/`
- `product-ops-service` 在 `platform-ops-service` ready 之前就开始上报 instance config，产生一次无意义的连接拒绝 WARN

已修：

- `quwoquan_service/services/platform-ops-service/cmd/api/main.go`
  - 新增 schema 路径解析 helper，优先命中工作区根下的
    `quwoquan_service/contracts/metadata/_control_plane/platform/config_schema.yaml`
- `quwoquan_ops/cli/beta/start_beta-local.sh`
  - 改为先启动并等待 `platform-ops`
  - 再启动 `product-ops`

验证结果：

- 当前轮次 `.qwq_output/local/beta-local/platform-ops.log` 不再出现 `load config_schema.yaml failed`
- 当前轮次 `.qwq_output/local/beta-local/product-ops.log` 不再出现 `config report failed`
- `go test ./cmd/api`
  - `quwoquan_service/services/platform-ops-service`
  - `quwoquan_service/services/product-ops-service`
  均通过

## 当前无阻断，但需识别为“过往产物”

### 6. gamma 过往 app launch 日志中的旧编译失败 / Lost connection

现状：

- `gamma-local` 当前健康检查全绿
- 过往 `.qwq_output/runs/gamma/*/app-launch-*.log` 中存在：
  - 旧代码编译失败
  - `Lost connection to device.`

判断：

- 这些记录属于过往运行产物，不代表当前 `gamma-local` 环境不可用
- 当前轮次 `stackctl health --target gamma-local --scope full` 已验证通过

处理口径：

- 排查当前 gamma 问题时，优先看本轮 report 目录与最新 log
- 过往 report 不作为当前环境故障证据，除非同一错误在最新轮次复现

## 待继续收口

### 7. cross-env health 探针面继续对齐

建议后续继续纳入 health 或 startup smoke 的接口族：

- `alpha-local`
  - 如后续 app 继续消费新的 discovery / notification 只读接口，应同步加入 mock smoke

- `gamma-local`
  - 当前 health 已覆盖主路径
  - `.qwq_output/local/gamma-local/runs` 已在本轮过往产物清理中移除
  - 当前需关注的是本轮 `.qwq_output/local/gamma-local/*.json` 证据，而非旧 runtime 目录

### 8. 过往 report / log 的保留策略

当前状态：

- 运行态日志已按轮次覆盖
- `.qwq_output/runs/**` 已执行 retention 收缩：每个环境/目标/命令分组仅保留最新一份时间戳报告

后续建议：

- 若后续新增固定命名报告目录，应继续与时间戳轮次目录分开管理
- 不要把过往报告 retention 与运行态日志轮换混为一谈

## 本轮修复涉及文件

- `quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh`
- `quwoquan_ops/cli/beta/start_beta-local.sh`
- `quwoquan_ops/cli/stackctl.py`
- `quwoquan_ops/cli/lib/mock_public_plane.py`
- `quwoquan_ops/lib/beta_manual_lifecycle.sh`
- `quwoquan_service/services/assistant-service/tests/ops/smoke/dev_assistant_beta_gateway.py`
- `quwoquan_service/services/platform-ops-service/cmd/api/main.go`
- `quwoquan_service/services/platform-ops-service/cmd/api/main_test.go`
- `quwoquan_app/scripts/device/start_beta-local.sh`
- `quwoquan_ops/tests/test_dev_up.py`
- `quwoquan_ops/tests/test_stackctl_up_runtime.py`

## 本轮验证证据

- `python3 -m unittest quwoquan_ops.tests.test_dev_up quwoquan_ops.tests.test_stackctl_up_runtime`
- `python3 quwoquan_ops/cli/stackctl.py health --target beta-local --scope full`
- `python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope full`
- beta 手工 HTTP smoke：
  - `/healthz`
  - `/v1/app-messages/unread-count`
  - `/v1/notifications/unread-count`
  - `/v1/content/feed/intersections?limit=2&channel=recommend`

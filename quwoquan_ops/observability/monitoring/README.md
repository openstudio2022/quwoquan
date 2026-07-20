# 生产观测栈

`prod-hosted` 的 service plane 使用 rootless Compose 启动 Prometheus 与
Alertmanager。配置只挂载仓库内规则；通知 URL 必须通过主机 Secret 文件注入，
不得提交到仓库。

```bash
export ALERTMANAGER_WEBHOOK_SECRET_FILE=/etc/quwoquan/secrets/alertmanager_webhook_url
export ALERT_INGEST_TOKEN_SECRET_FILE=/etc/quwoquan/secrets/alert_ingest_token
export PROD_SERVICE_NETWORK=quwoquan-prod-service_default
# 基础设施 exporter 家族（主机 / 容器 / 数据面）
export PODMAN_SOCKET_PATH=/run/user/1000/podman/podman.sock
export MONGODB_EXPORTER_URI="mongodb://host.containers.internal:19410"
export POSTGRES_EXPORTER_DSN="postgresql://quwoquan:quwoquan@host.containers.internal:19400/quwoquan?sslmode=disable"
export REDIS_EXPORTER_ADDR="redis://host.containers.internal:19420"
podman compose -f quwoquan_ops/observability/monitoring/docker-compose.prod.yml up -d
```

启动前必须确认：

- `ALERTMANAGER_WEBHOOK_SECRET_FILE` 是 rootless 运行账号可读的单行 HTTPS webhook URL；
- `ALERT_INGEST_TOKEN_SECRET_FILE` 是单行随机 token，与 service plane
  `platform-ops-service` 注入的 `ALERT_INGEST_TOKEN` 同值：Alertmanager 每个
  receiver 会把告警同时回流到
  `platform-ops-service:18088/control-plane/platform/alerts/ingest`
  （携带 `X-Alert-Ingest-Token`），形成 firing → ack → resolved 的值班闭环；
- `PROD_SERVICE_NETWORK` 是 prod service compose 创建的共享网络；观测栈必须加入同一网络，
  不得通过第二套 service DNS 或旧公开入口绕行；
- scrape 目标与 `prometheus.yml` 一致：service plane compose 服务
  （content/chat/user/assistant/product-ops/platform-ops/tag/entity）、
  独立进程（search-service、rtc-service）与 `recommendation-service:8000`
  能从观测栈网络访问 `/metrics`；
- 服务通过 `OTEL_EXPORTER_OTLP_ENDPOINT=otel-collector:4318` 把 trace/OTLP
  发到同一观测网络，collector 不承担业务事实存储；
- Prometheus 已加载 `alerts/quwoquan_alerts.yaml`，Alertmanager 已能收到一条
  测试告警并完成恢复通知（外部 webhook 与控制面 ingest 双路）；
- 生产部署 job 注入 `PROD_PROMETHEUS_URL`，供 `stackctl deploy` 做 SLO readback；
- 基础设施 exporter 家族随观测栈启动：`node-exporter`（主机 CPU/内存/磁盘/网络）、
  `podman-exporter`（rootless 容器级指标，经 `PODMAN_SOCKET_PATH` 用户级 socket）、
  `mongodb-exporter` / `postgres-exporter` / `redis-exporter`（数据面服务级 + 实例级）。
  对应告警在 `quwoquan_l4_infrastructure` 组（整体负荷 + 毛刺双阈值）。

告警规则的阈值与业务 SLO 仍以各自 metadata/policy 为准；本目录不复制阈值。

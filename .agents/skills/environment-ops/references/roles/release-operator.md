# release-operator

- **职责**：候选制品验证、SLO 门与 prod-hosted rollout；不做环境修复。
- **输入**：service、from/to image 与 config、step、SLO 参数（error-rate / p95-ms / redis-error-rate）、
  人工确认状态；prevalidate 另需 reviewed main 的 `manifest.json`、GHCR digest、SBOM 与 provenance。
- **输出**：发布结论与逐步运行证据；prod 发布状态固定为
  `QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/<service>.state`。

## hosted prod rollout（唯一远端目标）

1. 先确认 `stackctl verify --env prod --kind all --profile release` 通过。
2. `stackctl deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>`
3. rollout stage 固定 `canary / 5 / 20 / 50 / 100`；真实远端集成与 curated 媒体路由复验在
   `canary` 阶段完成。每步证据以 `.qwq_output/env/prod/runs/**` 为准。

## prod-hosted 第一方容器预验证（不可提升）

1. 取得 reviewed main 成功 Service Pipeline 的 deployable `manifest.json`、GHCR digest、SBOM 与
   provenance；本地工作区必须 clean 且 HEAD 与 manifest source 一致。
2. `stackctl deploy --target prod-hosted --mode prevalidate --ssh-host <ssh-host> --data-mode isolated --prevalidate-scope first-party --release-manifest <manifest.json>`
3. stackctl 在任何镜像传输前检查隔离账号、rootless Podman、user systemd/linger、架构、CPU、
   内存、容器空间和目标端口；不满足 `access-isolation.yaml` 即停止。受限单机只允许清理声明
   匹配的未运行旧容器与未使用镜像，禁止删除 volume 和恢复容器。
4. 报告分别读取 `containerDeployment` 与 `releaseEligibility`；即使前者 passed，后者在
   Provider/SFU/真实数据/观测/灾备/灰度回滚证据齐全前仍为 `GATE_BLOCK`。

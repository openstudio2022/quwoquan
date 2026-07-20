# Deliver → Prod 运行手册

## 1. 唯一生产主线

```text
reviewed PR → main
  → 02. Service Pipeline
  → immutable ReleaseManifest（全部生产 workload 的 OCI digest + SBOM + provenance）
  → 07. Deploy To Prod
  → gray-initial → carry-on → full
  → Prometheus readback + health/inspect/doctor
  → CAS ledger + immutable receipt
```

生产执行面是 `ssh-hosted + rootless Podman Compose`，不是 ACK。Kustomize 目录只做静态
部署描述校验，不参与当前生产 apply。Portal 只读展示配置、灰度、观测与审计，不提供
发布/回滚写入口。

正式发布单元为 `prod-stack`，覆盖
`prod_plane_access_isolation.yaml#rootlessGovernedComposeServices` 的全部 workload；
禁止继续把生产发布描述为 `seed-box` 两容器。

## 2. 真相源

- 拓扑与公网域名：`environment_topology_manifest.yaml`
- 平面账号、compose workload 与凭据边界：`prod_plane_access_isolation.yaml`
- 三阶段执行目标：`gray_rollout_stages.yaml`
- 分流维度与合成 canary：`gray_routing_policy.yaml`
- SLO 窗口、样本与阈值：`../policies/config-release/slo_thresholds.yaml`
- 不可变制品：`02. Service Pipeline` 的 `mainline-release-artifact`
- 当前运行版本：`resolve_prod_release_state.py` 对所有生产 service workload 的远端
  `podman inspect` 结果；版本不一致立即失败
- 发布状态：`QWQ_PROD_RELEASE_STATE_DIR/prod-stack.state`

`.qwq_output/` 只是可删除的报告、传输包和缓存，不得作为生产 ledger 的唯一存储。

## 3. 发布前条件

### 3.1 GitHub 与 runner

- 发布 commit 必须是合入 `main` 的唯一 PR merge 结果。
- 至少一名非作者审批人；`verify_release_governance.py` 生成与
  `gitSha + manifestDigest` 绑定的 receipt。
- 生产 job 只能运行在 `[self-hosted, macOS, prod-release]` 专用 runner。
- 所有 workflow 默认 `contents: read`；写包权限仅授予 main push 的镜像构建 job。
- 第三方 Action 必须固定完整 SHA，关键路径必须有 CODEOWNERS。

### 3.2 GitHub Environment / Repository 配置

生产环境必须配置：

- variable `PROD_PROMETHEUS_URL`
- variable `PROD_RELEASE_STATE_DIR`：专用 runner 可写的绝对持久路径
- 各平面 SSH secret（名称来自 `prod_plane_access_isolation.yaml`）
- `PROD_TEST_AUTH_TOKEN` 与 Portal OIDC variables

仓库/套餐支持时，同时启用 `main` required checks 和 `production` required reviewer。
即使平台保护不可用，PR 审批 receipt、专用 runner、统一 concurrency 和 stackctl
fail-closed 校验仍不可绕过。

### 3.3 本地与集成证据

```bash
make gate-local-gamma
python3 quwoquan_ops/cli/stackctl.py verify \
  --env prod --target prod-hosted --kind all --profile release
```

涉及 App 主旅程时还必须通过 `release_candidate` 的 API integration 与设备
user_acceptance。缺失依赖、设备、真实 seed 或远端探针时必须阻断，不能动态 skip。

## 4. Build Once

`02. Service Pipeline` 在 main push 上完成：

1. 从同一 git SHA 生成配置快照及其 SHA-256。
2. 为所有 governed workload 构建并推送镜像。
3. 生成 SPDX SBOM 与 SLSA provenance。
4. 记录 OCI digest；缺任一 workload、digest 或 attestation 时失败。
5. `finalize_mainline_release_artifact.py` 计算 `manifestDigest`，状态改为
   `deployable`。

生产端会再次验证：

- manifest 自摘要；
- checkout SHA；
- PR governance receipt；
- config 文件摘要；
- workload 集合；
- registry 中 digest、SBOM 与 provenance 实际存在。

禁止按 `latest`、本地重建、artifact fallback 或用户手填 target 版本发布。

## 5. 三阶段灰度

| 阶段 | step | 执行目标 | 真实流量 |
|---|---:|---|---|
| `gray-initial` | 5 | 独立 `*-gray` compose | 保留 canary user |
| `carry-on` | 25 | 独立 `*-gray` compose | canary + 目标 App 版本 |
| `full` | 100 | `*-prod` compose | 关闭 gray route，替换正式栈 |

`gray-initial/carry-on` 不会提前替换 prod workload。候选 gray 栈健康后，发布脚本只重载
稳定 prod Caddy 的 IaC 路由；`full` 成功 apply 时关闭 gray route，并回收 gray compose。

每阶段由 `stackctl`：

1. 获取全局 `flock`；
2. 校验 ledger CAS 与阶段顺序；
3. 按 OCI digest 拉取并以发布版本本地标记；
4. apply 全部平面；
5. 从公网 HTTPS API 发送至少 100 个命中 gray policy 的 canary 请求；
6. 等待策略驻留时间；
7. 从 Prometheus 查询真实 RED/Redis/推荐指标；
8. 执行 health、inspect、doctor 和初始阶段页面 smoke；
9. 原子提交 ledger 与不可变 receipt。

调用方不得传入 `error_rate/p95/redis_error_rate`，这些值只允许来自 Prometheus。

## 6. 执行入口

推荐入口：

- 自动全链：`.github/workflows/deploy-prod-auto.yml`
- 人工单阶段恢复/复核：`.github/workflows/deploy-prod-gray.yml`

人工 workflow 只接收 `Service Pipeline run id`、云厂商、阶段与 dry-run；当前版本来自
远端容器，目标版本来自 ReleaseManifest。

`stackctl` 等价命令（由受保护 workflow 调用）：

```bash
python3 quwoquan_ops/cli/stackctl.py deploy \
  --target prod-hosted \
  --cloud-provider aliyun \
  --service prod-stack \
  --from-image <remote-current> \
  --to-image <manifest-image-version> \
  --from-config <remote-current> \
  --to-config <manifest-config-version> \
  --stage gray-initial \
  --step 5 \
  --release-manifest <governed-artifact>/manifest.json
```

非 dry-run 还必须具备 `PROMETHEUS_URL` 与绝对
`QWQ_PROD_RELEASE_STATE_DIR`，否则命令直接失败。

## 7. 回滚

任一平面 apply、canary、SLO 或 post-deploy 检查失败时：

1. stackctl 使用已保留的 previous 本地镜像标签重新渲染全部平面；
2. 全平面恢复旧 image/config；
3. 移除候选 gray 栈；
4. 再执行 rollback health；
5. ledger 记为 `rolled_back`；回滚或回滚后健康失败则记
   `rollback_failed` 并阻断后续发布。

生产主机在 full/rollback 后只保留 current 与 previous 两个发布镜像标签；持久
release artifact 同样只保留最近两个。

## 8. 冷启动与边缘安全

- prod Caddy 固定 digest，监听 80/443，使用公网域名自动 ACME，不允许
  `local_certs` / `tls internal`。
- `api/realtime/ops/cdn/upload` 域名只来自 topology。
- Portal 启用 HSTS、CSP、frame deny、nosniff 和 SPA fallback。
- gray Caddy 只在同机 29000 提供 HTTP upstream，不申请公网证书。
- runtime config、Portal、legal、media、model cache 和 integration APNs/FCM 凭据均由
  render/sync 包显式挂载；凭据缺失、权限错误或符号链接立即失败。

## 9. 验收证据

每次生产 run 必须归档：

- ReleaseManifest、governance receipt、manifest digest；
- 各镜像 digest/SBOM/provenance；
- canary 请求摘要与 Prometheus 原始查询/值；
- apply/rollback stdout、health/inspect/doctor；
- CAS generation、release receipt id；
- full 后 gray cleanup 与 current/previous retention 结果。

没有真实生产凭据时只能完成 dry-run 和本地契约验证，不得把历史报告或合成成功写成
本轮生产演练证据。

# 群头像商用端到端全矩阵执行手册

本文档与 [`avatar-e2e-validation.md`](./avatar-e2e-validation.md) 同源。四个 target
未全部产出非 dry-run、可追溯证据前，结论保持 `GATE_BLOCK`。

## 必选矩阵

| 环境 | target | 必须证据 |
|---|---|---|
| alpha | `alpha-local` | 本地契约、probe、Android/iOS 设备报告 |
| beta | `beta-local` | Remote 网关、probe、Android/iOS Patrol 报告 |
| gamma | `gamma-local` | stackctl 启动的本地组合拓扑、probe、Android/iOS Patrol 报告 |
| prod | `prod-hosted` | 同一 release/config hash 下 `gray-initial → carry-on → full` 的 probe、双端报告与回滚证据 |

每条报告必须使用 `scenario=chat.group_avatar.sync_display_e2e*`、`status=passed`，
并包含真实服务与 UI 证据。`dry-run`、synthetic device、空文件或仅有命令日志均不能替代。

## 前置条件

- 环境 URL 与 target 只从
  [`environment_topology_manifest.yaml`](../../../../../quwoquan_ops/environments/environment_topology_manifest.yaml)
  和 stackctl 解析，不手写远端 gamma 地址。
- Android/iOS runner 必须能执行 Flutter/Patrol；prod 证据须使用受控发布凭据。
- gamma 仅使用 `gamma-local`；远端 gamma、ECS gamma 与 `cloud-gamma-*` 已退役。

## 执行入口

```bash
# gamma-local 组合栈与本地聚合报告
python3 quwoquan_ops/cli/stackctl.py up --env gamma
python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gamma/run_local_gamma_avatar_e2e.py --help

# 单环境 probe 与设备矩阵
python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/smoke/run_chat_avatar_e2e_probe.py --help
python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/ci/run_chat_avatar_device_matrix.py --help
```

四环境报告写入一个 manifest：

```yaml
schema: chat-avatar-commercial-matrix-manifest
alpha_local:
  probe: <path>
  android: <path>
  ios: <path>
beta_local:
  probe: <path>
  android: <path>
  ios: <path>
gamma_local:
  aggregate: <path>
prod_hosted:
  probe: <path>
  android: <path>
  ios: <path>
```

机器校验：

```bash
make verify-chat-avatar-commercial-matrix \
  COMMERCIAL_MATRIX_MANIFEST=.qwq_output/env/repo/runs/commercial-matrix-chat-avatar/manifest.yaml
```

退出码 `0` 才允许更新 [`acceptance.yaml`](./acceptance.yaml) 与
[`avatar-e2e-validation.md`](./avatar-e2e-validation.md) 的执行证据；退出码 `2`
表示矩阵仍为 `GATE_BLOCK`。

## 发布前检查

- [ ] `alpha-local`、`beta-local`、`gamma-local`、`prod-hosted` 恰好各一份。
- [ ] Android 与 iOS 均为真实设备或受控模拟器报告，且 `status=passed`。
- [ ] prod 三个 rollout stage 绑定同一 release/config hash，并有失败停止与回滚证据。
- [ ] manifest 校验退出码为 `0`，文档状态与证据一致。

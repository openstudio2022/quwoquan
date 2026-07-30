# gamma-local target

本目录定义提交前本地 gamma 镜像预测试的反代与设备连接说明。它不是额外环境；服务仍使用 `APP_ENV=gamma`，App 使用 `APP_RUNTIME_ENV=gamma` 的 production Remote composition，运行时不存在 Mock/Remote 切换。

## 一键启动

```bash
python3 quwoquan_ops/cli/stackctl.py up --target gamma-local --skip-app
```

默认会生成：

- `QWQ_DEPLOY_WORK_ROOT/gamma-local/packages/services/<service>`：由各服务 `config/schema.yaml + environments/gamma/config.yaml` 生成的自治包。
- `QWQ_DEPLOY_WORK_ROOT/gamma-local/rendered/config-root`：启动器校验 package provenance 后汇集的只读容器挂载目录；不是配置真相源。
- `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/cache/media`：本地 media/CDN 测试目录。
- `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/`：仅保存可删除的进程状态；后续 gate 证据写入 `env/gamma/runs/**`。

`quwoquan_data/control_plane/governance/taxonomy` 是受版本控制的唯一标签真相源。启动脚本只读导入该树；目录缺失时直接失败，不在运行期生成 `publish/tags` 副本。

`user-service` 的微信、支付宝、QQ 与阿里云一键登录必须由部署密钥系统注入真实凭据：`WECHAT_OAUTH_*`、`ALIPAY_OAUTH_*`、`QQ_OAUTH_APP_ID`、`ALIYUN_DYPNS_ACCESS_KEY_*`。本地 Gamma 不生成占位密钥，也不以 Mock provider 替代；缺任一已暴露能力的凭据时 Compose 在启动前失败。

## 实际运行形态

`local-gamma mirror` 的运行时口径是单机 `docker compose` 单栈，不是 K8s，也没有 Pod 概念。

- Ops Compose 只定义数据库、对象存储、external workload 与统一 `gamma-proxy`；第一方 workload 分别由 `services/<service>/deploy/compose.yaml` 自治拥有，启动器扫描这些片段完成装配，不维护服务名册。
- `mongo-init` 与 `object-storage-init` 是一次性 init 容器；`object-storage` 是固定版本的本地 S3-compatible 服务。本地 JWT、设备票据、对象存储密钥和 TLS 物料只在仓外 `QWQ_DEPLOY_WORK_ROOT/gamma-local/`，不会写入 `.qwq_output` 或仓库。
- 对外入口以 `gamma-proxy` 为主：`19000` 提供 API edge，`19100` 提供 media edge；`19010` 直连 `product-ops-service`。

## DNS

需要让运行 App 的设备解析以下域名到本机 mirror：

```text
api.gamma.quwoquan.com
ops.gamma.quwoquan.com
cdn.gamma.quwoquan.com
cdn.gamma.quwoquan.com
cdn.gamma.quwoquan.com
upload.gamma.quwoquan.com
```

建议：

- macOS / iOS Simulator：直接使用 topology 生成的 canonical authority；公网 DNS 将非生产环境解析到 loopback。
- Android 模拟器与真机：保留 canonical authority，由 launcher / Patrol runner 对 target 端口执行 `adb reverse`；禁止改写为私有 IP 或 `.localhost`。
- DNS 或公共 CA 未就绪时 fail-fast，不通过 `/etc/hosts`、私有 CA 或关闭证书校验绕过。

## TLS

本地公开入口必须使用 `*.gamma.quwoquan.com` 的 DNS-01 公共 CA 证书。禁止
Caddy internal CA、`mkcert`、关闭证书校验或临时 HTTP runtime define。

## 本地覆盖边界

本地 mirror 覆盖提交前 `T1 -> T4` 左移：

- `T1`：静态、metadata、拓扑、环境包、seed manifest。
- `T2`：模块、Widget、Provider/Journey。
- `T3`：真实 API、真实存储副作用、错误响应与 generated client/typed Remote Facet。
- `T4`：模拟器/真机 Patrol 核心旅程。

本地通过不替代云侧 gamma、prod 的 K8s、Ingress/LB、Secret、云观测、SLO、回滚与真实分发验证。

# Local Gamma Mirror

本目录定义提交前本地 gamma 镜像预测试的反代与设备连接说明。它不是第六个环境；服务仍使用 `APP_ENV=gamma`，App 仍使用 `APP_RUNTIME_ENV=gamma`、`APP_DATA_SOURCE=remote`。

## 一键启动

```bash
scripts/start_local_gamma_mirror.sh
```

默认会生成：

- `artifacts/local-gamma/config-root`：满足 `CONFIG_ROOT` 与 `CONFIG_VERSION=local-gamma-v1` 的本地配置树。
- `artifacts/local-gamma/media`：本地 media/CDN 测试目录。
- `artifacts/local-gamma/report.json`：后续 gate 汇总报告。

## DNS

需要让运行 App 的设备解析以下域名到本机 mirror：

```text
gamma-api.quwoquan-env.test
gamma-product-ops.quwoquan-env.test
gamma-avatar.quwoquan-env.test
gamma-image.quwoquan-env.test
gamma-video.quwoquan-env.test
gamma-upload.quwoquan-env.test
```

建议：

- iOS 模拟器：可先在 macOS `/etc/hosts` 映射到 `127.0.0.1`。
- Android 模拟器：优先使用 `10.0.2.2` 或本机局域网 IP；如坚持域名，需要让模拟器 DNS 可解析到宿主机。
- 真机：使用局域网 DNS、路由器 DNS、dnsmasq/CoreDNS 或 VPN 分流；macOS `/etc/hosts` 不会影响真机。

## TLS

默认 `Caddyfile` 使用 Caddy internal CA。真机/模拟器必须信任本地 CA，否则 HTTPS/WSS 会失败。

可选方案：

- 使用 Caddy internal CA，并将生成的 root CA 安装到设备。
- 使用 `mkcert` 生成 `*.quwoquan-env.test` 证书后替换 `Caddyfile` 的 `tls internal`。
- 仅调试时使用 HTTP runtime define，但这会偏离 committed gamma runtime config，不能作为最终提交前报告。

## 本地覆盖边界

本地 mirror 覆盖提交前 `T1 -> T4` 左移：

- `T1`：静态、metadata、拓扑、环境包、seed manifest。
- `T2`：模块、Widget、Provider/Journey。
- `T3`：真实 API、真实存储副作用、错误响应与 RemoteRepository。
- `T4`：模拟器/真机 Patrol 核心旅程。

本地通过不替代云侧 gamma、prod-gray、prod 的 K8s、Ingress/LB、Secret、云观测、SLO、回滚与真实分发验证。

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

- macOS / iOS Simulator：直接使用 topology 生成的 canonical authority，由 stackctl 生成 target-scoped resolver handoff。
- Android 模拟器与受管真机：保留 canonical authority，由 stackctl/launcher 安装 resolver handoff、信任材料并对 target 端口执行 `adb reverse`；禁止改写为私有 IP、`.localhost` 或 App 内 fallback。
- resolver 或 local-managed CA 未就绪时 fail-fast；禁止人工修改 App/test URL、关闭证书校验或在源码中打包 CA。

## TLS

本地公开入口使用 topology 声明的 `local-managed` profile。stackctl 在
`QWQ_DEPLOY_WORK_ROOT/gamma-local/` 生成并验证 target-scoped CA、叶证书、SAN
和受管设备信任回执；Prod package 必须拒绝这些材料。禁止 Caddy 自发签发、
`mkcert`、关闭证书校验或临时 HTTP runtime define。

## 真机登录取验证码（OTP）

本地 Gamma 的短信 Provider 是 `ext.sms.local_capture` 替代实现：验证码为安全随机
6 位，不真发短信，也不写入日志、API 回包或 receipt。规格明确禁止固定万能码与
App `debugCode`（见 `four-environment-commercial-login-maturity` L3 spec）。

真机手机号登录步骤：

1. 在设备 App 上输入手机号并点发送，进入验证码页。
2. **立即**在本机交互终端执行：

   ```bash
   python3 quwoquan_ops/cli/stackctl.py provider-debug otp-read --target gamma-local
   ```

3. 按提示输入同一手机号（隐藏输入；`180xxxxxxxx` 或 `+86180xxxxxxxx` 均可）。
4. 终端 TTY 显示一行 `OTP: ******`，把 6 位码填进设备 App。

注意：

- 读取是**一次性**的，读完即从 substitute 内存删除；超时或读空先在 App 重发再读。
- 只支持 `alpha-local|beta-local|gamma-local`，且要求交互 TTY；OTP 只写 `/dev/tty`，
  不进入命令 JSON 输出。
- 输错会得到 `USER.AUTH.otp_mismatch`（「验证码不正确，请重新输入」），重发后重读即可。

## 本地覆盖边界

本地 mirror 覆盖提交前 repository gate 到 device-UAT 左移：

- `repository-gate`：静态、metadata、拓扑、不可变环境包与 immutable release 绑定。
- `local-contract`：模块、Widget、Provider/Journey。
- `release-consumer`：真实 API、真实存储副作用、错误响应与 generated client/typed Remote Facet。
- `device-UAT`：模拟器/真机 Patrol 核心旅程。

本地通过不替代云侧 gamma、prod 的 K8s、Ingress/LB、Secret、云观测、SLO、回滚与真实分发验证。

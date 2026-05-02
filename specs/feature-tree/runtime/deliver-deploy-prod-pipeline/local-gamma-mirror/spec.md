# L3 特性：local-gamma-mirror

## 功能说明

`local-gamma-mirror` 是提交前本地预测试环境：在开发机通过 Docker 镜像栈、DNS/TLS 反代、gamma seed manifest 与真机/模拟器 runner，把 `T1 -> T4` 验证尽量左移到本地完成。

本特性不新增运行环境枚举。服务仍以 `APP_ENV=gamma` 启动，端侧仍以 `APP_RUNTIME_ENV=gamma`、`APP_DATA_SOURCE=remote` 运行；本地差异只体现在 endpoint、DNS/TLS、镜像编排和测试报告。

## 范围

- 本地 gamma 镜像栈：MongoDB、Redis、Postgres、核心服务镜像、media static、TLS reverse proxy。
- 本地配置版本：满足 `gamma` 必填 `CONFIG_VERSION` 的配置快照或等价挂载结构。
- 本地 seed/reset：只消费 `app_gamma_seed_manifest.json` 与 metadata fixtures，不在脚本中临时造业务数据。
- 本地 `T3`：真实 HTTP API、真实存储副作用、错误码、响应 schema、RemoteRepository 解码。
- 本地 `T4`：模拟器/真机 Patrol 核心旅程，覆盖 IME、权限、媒体、弱网、横竖屏等设备能力路径。
- 提交前报告：`artifacts/local-gamma/report.json` 记录 commit、镜像、配置、设备、DNS/TLS 与 `T1 -> T4` 结果。

## Out of Scope

- 不替代云侧 gamma 的 K8s、Ingress/LB、Secret、云观测、云网络策略与多云 overlay 验证。
- 不替代 prod-gray 的真实灰度流量、SLO 卡点、审批与回滚演练。
- 不新增 `local-gamma` 配置目录、`APP_ENV` 枚举或第四份 seed manifest。
- 不在生产包中引入 test fixture、seed reset 或本地 mirror URL。

## 验收标准概要

- A1：规格、设计、验收与计划已落地，明确本地 `T1 -> T4` 左移覆盖与云端不可替代边界。
- A2：`local-gamma` 文档明确不新增第六环境，endpoint 覆盖只通过本地脚本、runtime define 或未入库 overlay 注入。
- A3：本地 Docker mirror 可启动 `gamma` 语义服务，满足 `CONFIG_VERSION`、依赖、health、DNS/TLS 与 media endpoint 前置检查。
- A4：本地 `T3` runner 使用 `app_gamma_seed_manifest.json` 验证真实 API、真实存储副作用、错误响应和 RemoteRepository 边界。
- A5：本地 `T4` runner 统一 App 与测试进程 endpoint，至少在一台模拟器或真机完成 Patrol 核心旅程。
- A6：`gate-local-gamma` 生成 `artifacts/local-gamma/report.json`，并成为后续 commit 前强制准入要求。

# api-edge Agent Guide

本目录是 metadata domain `gateway` 的统一业务 HTTP 入口；同时遵守仓库根与
`quwoquan_service/AGENTS.md`。

- `contracts/edge_security/rate_limit_bucket` 是限流决定、错误与 Redis key 的唯一真相源。
- 请求顺序固定为 credential verification -> generated operation authorization ->
  shared admission -> owner proxy；禁止进程内 limiter、失败回退计数器或绕过 ContractGraph。
- Caddy 只负责 TLS、静态资源和可信代理属性覆盖；不得在 Caddy 复制业务路由表或限流策略。
- stable/gray 只是 `prod` rollout stage，必须共享同一 Redis admission scene，key 不得包含 stage/instance。
- 配置、部署和四环境入口均由本服务自治；环境之间禁止继承。
- 禁止手改 `generated/`；先改 contracts，再执行 metadata/codegen 与三层验证。

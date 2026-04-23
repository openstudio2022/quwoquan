# Runtime 横切能力设计

本目录用于沉淀 `quwoquan_service` 的横切面 runtime 设计，作为各业务服务在媒体、同步、实时、事件封装与统一 URL 规范上的公共基线。

## 目标

- 为 `user-service`、`chat-service`、`content-service` 等业务服务提供统一公共能力。
- 冻结跨服务共享的模型、协议、命名、URL 规范与运行时边界。
- 为后续 `PRD -> design -> dev` 提供可引用、可拆分、可验证的设计前置文档。

## 不在本目录解决的问题

- 不定义单个业务能力的最终产品规则，例如某个具体页面的交互细节。
- 不替代 `contracts/metadata/` 的契约真相源地位。
- 不替代各业务服务 `spec.md` 中的领域边界与 API 责任。

## 与其他目录的关系

- `quwoquan_service/contracts/metadata/`：接口、字段、错误码、投影契约的唯一真相源。
- `quwoquan_service/specs/<service>/spec.md`：业务服务级规格与边界。
- `quwoquan_service/specs/runtime/`：横切公共能力的设计基线。

## 阅读顺序

1. `00-runtime-overview.md`
2. `01-runtime-boundaries.md`
3. `02-object-identity-and-url-spec.md`
4. `03-event-envelope-and-versioning.md`
5. `04-observability-and-governance.md`
6. `media/`
7. `sync/`
8. `realtime/`
9. `appendices/`

## 当前能力域

- `media/`：上传、存储、CDN、资产引用、头像与图片/视频派生策略。
- `sync/`：统一同步流、patch envelope、cursor、gap fill、幂等与补偿。
- `realtime/`：在线通知、订阅路由、WebSocket / Push 降级策略。
- `appendices/`：术语表、决策记录、迁移计划。

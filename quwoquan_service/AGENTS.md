# quwoquan_service Codex Guide

在 `quwoquan_service/` 工作时，除仓库根 `AGENTS.md` 外，先阅读仓库根 `.cursor/rules/` 与服务契约入口：

1. `quwoquan_service/contracts/metadata/README.md`
2. `.cursor/rules/01-arch-constraints.mdc`
3. `.cursor/rules/10-runtime-error-cutover.mdc`

## 服务端硬约束

- 先 metadata，后 verify/codegen，再写实现；不要直接手改生成文件。
- `contracts/metadata/**` 是字段、错误码、path、operation、surface、route 与契约测试口径的唯一真相源。
- DDD 依赖方向固定：`domain <- application <- adapters <- infrastructure`。
- 数据库驱动、缓存驱动、外部存储 SDK 只应出现在 `infrastructure/` 与测试。
- HTTP 错误边界统一走 runtime errors；不要自造并行错误响应结构。
- 新增/变更 API、事件、字段、错误码时，要同步评估 app codegen 与 contract tests。
- 新增 API、消费者、导入器、推荐投影或后台任务必须同步声明 metrics、trace/request id、日志脱敏、SLO、告警阈值、配置来源与回滚策略。
- 四环境配置必须来自统一 topology/config/seed manifest；不要手写端口、host、public URL 或环境分支。
- 当前阶段未上线：错误领域模型、错误 API 契约、错误存储抽象或临时兼容直接纠正，不保留 shim、fallback 或旧路径兼容。

## 错误码与可观测

- 新增或修改错误时，先改 metadata `errors.yaml`，定义 stable code、HTTP status、用户提示/l10n、`recovery.action`、`disruptionLevel`、Go/Dart 常量，再 verify/codegen。
- HTTP 边界必须通过 runtime errors helper 输出 `RuntimeErrorResponse`，保留 request id、trace id、operation id 与脱敏 context；禁止返回自造 `{error: ...}` 或第三方原始错误。
- stable code 使用 `MODULE.KIND.REASON`；动态字段、第三方错误、用户输入、堆栈信息只进入脱敏 string-only `context.attributes` 或内部日志，不能进入 code 或用户提示。
- metrics/log/trace 必须按 code、domain、operation、surface、HTTP status、recovery action、disruption level、环境和版本聚合，支持 SLO、告警和运营分析。
- 用户可恢复错误、权限/登录错误、业务校验错误、依赖错误、服务不可用错误、数据一致性错误必须能区分告警级别与恢复路径。

## 典型触发与 E2E

- 用户说“新增 API、字段、错误码、导入器、推荐投影、行为事件、真实存储、服务观测”时，默认加载本文件。
- 若服务输出被 App 消费，必须同步评估 App codegen、RemoteRepository、`local_contract` Mock/Widget 和 `api_integration` 端云证据。
- 若服务消费数据工程产物或影响环境发布，必须把 Data importer、stackctl 和观测证据纳入出口。

## Review 与测试要求

- 每个服务改动都要覆盖 `local_contract` metadata/static/domain/application 模块、`api_integration` HTTP/真实存储/消息链路，涉及用户旅程或发布前验证时补 `user_acceptance`。
- 服务端 `api_integration` 真实 API 行为必须能回到 App 端 `local_contract` Mock/Provider/Widget 对应断言，避免 Mock 与 Remote 分裂。
- 错误码链路的 `local_contract` 覆盖 metadata/codegen/硬编码扫描，`api_integration` 覆盖 HTTP 响应、trace/request id、Remote 映射输入；涉及用户恢复体验时补 App `user_acceptance`。
- 内容 importer、推荐 HotPath、行为事件、特征投影、AB 分桶和运营指标必须保持同一 trace/subject/referral 语义，不得新增双轨标识。

## 推荐验证

- metadata 变更后优先执行：`make verify-metadata`
- 需要生成产物时执行：`make codegen` 与必要的 `make codegen-app`
- 结构化错误边界变化时执行：`dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`
- 再运行对应 Go 测试与 `make gate`
- 环境、部署或拓扑相关改动使用 `python3 quwoquan_ops/cli/stackctl.py package/verify/health/inspect` 收集证据。

# quwoquan_service Codex Guide

在 `quwoquan_service/` 工作时，除仓库根 `AGENTS.md` 外，先阅读服务契约入口：

1. `quwoquan_service/contracts/metadata/README.md`

## 服务端硬约束

- 先 metadata，后 verify/codegen，再写实现；不要直接手改生成文件。
- Python/Shell 脚本只落在 `scripts/{contracts,codegen,runtime,verify,tools}/` 或 `scripts/<kebab-service>/[<context>/<object>/]`；`contracts/` 只放 build/sync/generate，禁止 pure verifier；`verify/` 禁止写回 metadata。详见 `scripts/README.md`。
- `scripts/contracts/build_service_contract_view.py` 产出带逐文件 SHA 与 canonical `sourcePaths` provenance 的不可变 byte snapshot，不得包含 live symlink。负例测试只能修改自己的 snapshot 副本；如果 canonical source 在构建期漂移，builder 必须删除半成品并 fail-closed，loader/readiness 必须使用 provenance 还原并验证真实 object-local owner，禁止回退到路径猜测或 symlink 穿透。
- 校验契约图只用 `make verify-contract-graph`，它按 `--metadata-dir "$(CONTRACT_VIEW)" --profile baseline` 调用 `tools/qwq_contract validate`。裸调 `go run ./tools/qwq_contract validate --repo-root <repo>`（不给 metadata-dir 与 profile）会落到另一套默认口径，产出数百条 `CONTRACT.APP_SURFACE.UNKNOWN_OPERATION` 与 `CONTRACT.ENUM.DEAD_DEFINITION`——这些与真实契约状态无关，不是 operation 断链，不要据此追查或改契约。
- 判定「契约声明了某实现事实但无实现」时，不得以声明专用标识符在实现中查无作为依据：实现从不包含声明专用词（`cdn_purge` 的实现是 `DELETE FROM user_devices`，`sanitizeForLog` 之外另有 `AppLogRedactor` 与元数据生成的 `runtime_log_catalog.g.dart` 在做同一件事）。必须先枚举该行为在本库可能的实现形态——同义标识符、上层封装名、另一条 codegen 管线、SQL/DDL 等不含业务词的形式、`generated/**` 内的生成实现（`storage.yaml` 的 indexes 直接生成 `SetName(...)`、errors 有数据驱动目录发射）、以及 `quwoquan_app/**` 内的端侧实现——全部落空后缺失才成立。手工推翻自动判定时必须写明所依据的搜索范围，否则范围性遗漏不可见。已按此判据推翻多例误报，其真实性质均为「逐对象手写或生成实现已存在，缺的是一致性与可验证性」。
- 上一条的失效方式已固定成一种形态，反复出现五次且**每次都往「有缺口」偏**：只覆盖了声明侧或实现侧的**一种命名/存放形态**就下结论。五次的具体形态是——只扫 `.sql` 而漏掉 Go/Python 内嵌的建表字符串（`skill_surface_placements`、`reports` 等的 DDL 就在 Go 里）；同名表在仓内有多处 `CREATE TABLE` 时用首个正则命中锁错表体；`collections:` 下是 YAML key 而非带 `name` 的列表项；事件声明用 PascalCase 而实现发射点分串；只看 `CREATE TABLE` 而漏掉后续 `ALTER TABLE ... RENAME COLUMN`（`045_persona_actor_single_track.up.sql` 把 8 个已退役 actor 词汇的列名逐个改成 `*_persona_id`，只看建表会得出 8 条不存在的列名漂移）。所以下结论前必须问：这个事实在**声明侧**有几种写法、在**实现侧**有几种存放位置，两侧都枚举完了吗。反过来，拿一条**不可能为真的结果**去反推方法是最有效的自检——「`personas` 表缺 `persona_id` 列」这种结果一出现就说明方法坏了，而不是仓库坏了。
- codegen 输入只来自对象自己的 contracts；禁止新增服务级 `codegen_*manifest*`、对象路径清单或输出路径注册表。
- 一旦服务生成 errors，必须为每个 `contracts/<context>/<object>/errors.yaml` 生成独立的 `generated/<context>/<object>/errors.*`；禁止将整个 domain 的错误聚合到主对象包。
- 跨服务公共契约可生成到实际消费对象，但 header 必须指向存在的外部对象契约；这只是可重建客户端，不得复制或改写外部真相源。
- `services/<service>/contracts/**` 是该服务字段、错误码、path、operation、surface、route 与契约测试口径的唯一真相源；`contracts/metadata/**` 只保留跨服务 schema、共享协议和值定义。
- 目录组织轴固定为 `services/<service>/internal/<context>/<object>/<layer>`；domain 从该服务 `contracts/domain.yaml` 推导，context/object 从路径推导，kind 只在对象 `object.yaml` 声明。
- 声明 `operations.yaml.api_routes` 的对象必须拥有同路径真实源码；禁止把对象实现集中到同服务“主对象”目录，也禁止用空目录或占位文件冒充 source owner。
- DDD 依赖方向固定：`adapters/inbound -> application -> domain`，`infrastructure` 只实现 application/domain port。
- 对象的 `adapters`/`infrastructure` 属于私有实现，禁止被兄弟对象直接导入；跨对象只依赖对方的 domain/application port 或事件，多个对象的 adapter 只在 `cmd` 组合。
- 数据库驱动、缓存驱动、外部存储 SDK 只应出现在 `infrastructure/` 与测试。
- HTTP 错误边界统一走 runtime errors；不要自造并行错误响应结构。
- 新增/变更 API、事件、字段、错误码时，要同步评估 app codegen 与 contract tests。
- 新增 API、消费者、导入器、推荐投影或后台任务必须同步声明 metrics、trace/request id、日志脱敏、SLO、告警阈值、配置来源与回滚策略。
- 四环境配置必须来自服务内 `config/schema.yaml` 和 `environments/<env>/config.yaml`；稳定资源归服务 `resources/`，环境资源只保存 seed/release/artifact 引用。
- alpha/beta/gamma/prod 的第一方业务对象只允许由 canonical immutable release importer 激活；环境资源、启动器、T3/UAT 和测试 fixture 不得直写业务存储或进入公开 feed/homepage/profile。基础设施 canary 必须与业务投影物理隔离。
- 第一方部署基线归服务 `deploy/base`，四环境部署入口归 `environments/<env>/deploy`；Ops 只做跨服务装配与外部 workload，不维护第一方 workload/topology 注册表。
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
- `local_contract` 只使用对象级 typed builder/generator、固定 seed/clock/ID 与最小 wire/golden；`api_integration` 只通过 application command/provider-state 构造最小前置状态。direct storage 仅限 persistence adapter、migration 与 corruption recovery 专项测试，不得作为一般 API 或环境数据准备入口。
- 单个结构化 fixture 不得超过 64 KiB、500 个 scalar leaf 或 100 项单数组，同一 object support 下总量不得超过 256 KiB；超限改为 builder、固定 seed generator、immutable release 或独立 corpus，不得建立 fixture allowlist。
- 独立 benchmark/eval corpus 必须有 manifest、digest 与 case count，只保存评测输入和期望；不得携带 `seedSets`、`repositoryExpectations`、`requiresSeedReset` 或环境 Repository 选择。执行模式、Actor 与可变状态由 runner/capability 控制面拥有。
- 对象测试必须位于 `tests/<layer>/<context>/<object>/`；共享启动器只能放 `tests/support`，不得把兄弟对象测试借放到主对象目录。
- 服务端 `api_integration` 真实 API 行为必须能回到 App 端 `local_contract` Mock/Provider/Widget 对应断言，避免 Mock 与 Remote 分裂。
- 错误码链路的 `local_contract` 覆盖 metadata/codegen/硬编码扫描，`api_integration` 覆盖 HTTP 响应、trace/request id、Remote 映射输入；涉及用户恢复体验时补 App `user_acceptance`。
- 内容 importer、推荐 HotPath、行为事件、特征投影、AB 分桶和运营指标必须保持同一 trace/subject/referral 语义，不得新增双轨标识。

## 推荐验证

- metadata 变更后优先执行：`make verify-metadata`
- 服务目录、配置、资源、部署装配或外部 capability 变更先执行：`make verify-service-architecture`
- 需要生成产物时执行：`make codegen` 与必要的 `make codegen-app`
- 结构化错误边界变化时执行：`dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`
- 再运行对应 Go 测试与 `make gate`
- 环境、部署或拓扑相关改动使用 `python3 quwoquan_ops/cli/stackctl.py package/verify/health/inspect` 收集证据。

# quwoquan_service Agent Guide

本文件与根 `AGENTS.md` 同时生效，只声明 `quwoquan_service/**` 每次变更都成立的服务不变量。进入具体服务时再读其最近 `AGENTS.md`；功能事实、特定 gate 与实现方法从 owner manifest 指向的 Feature/design/contracts 加载。

## 契约与生成顺序

- 先读 [`contracts/metadata/README.md`](contracts/metadata/README.md)。`services/<service>/contracts/**` 是该服务对象、wire 字段、错误码、path、operation、surface、route 和 decoder context 的唯一 authoring source；`contracts/metadata/**` 只拥有跨服务 schema、共享协议和值定义。
- 变更顺序固定为 contracts/metadata → verify → codegen → implementation → tests。禁止手改 generated 产物、新建输出路径 registry/manifest 或让一个主对象代生整个 domain 的 errors。
- 字段可空性、闭集枚举、默认值和必填性只由对象 contract 声明。生成器和读侧不得补未声明默认、将未知值放宽为成功或以双键解码维持错误 wire。
- 服务 contract view 是带 source path/摘要 provenance 的可重建投影，不是第二真相源。builder/loader 对半成品、source 漂移、symlink 穿透、摘要不匹配均 fail-closed；具体格式见 `scripts/README.md` 与所属系统设计。

## 对象目录与依赖

- 生产代码轴固定为 `services/<service>/internal/<context>/<object>/<layer>`。domain 由 `contracts/domain.yaml` 派生，context/object 由 contract path 派生，kind 只在对象 `object.yaml` 声明。
- 声明 `operations.yaml.api_routes` 的对象必须拥有同归属的真实源码；禁止集中到“主对象”、空目录、占位文件或手工 owner 登记表。
- 依赖方向为 `adapters/inbound -> application -> domain`，`infrastructure` 只实现 application/domain port。对象 adapters/infrastructure 是私有实现；跨对象只依赖对方 domain/application public port 或 event，多对象 adapter 只在 `cmd` 组合。
- 数据库、缓存和外部存储 SDK 只出现于 infrastructure/测试。服务分层、CQRS、结果状态与显式配置的 canonical 决策见 [`runtime/system-architecture-and-engineering-guide`](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md)，不在本文件复制语言级规则。
- Python/Shell 脚本只落在 `scripts/{contracts,codegen,runtime,verify,tools}/` 或 `scripts/<kebab-service>/[<context>/<object>/]`，角色与写入边界见 `scripts/README.md`。

## 错误、配置与发布边界

- 新增/修改错误先改对象 `errors.yaml`，声明 stable `MODULE.KIND.REASON`、HTTP status、用户提示/l10n、recovery action、disruption level 与 Go/Dart 常量，再 verify/codegen。
- HTTP 边界统一通过 runtime errors helper 输出 `RuntimeErrorResponse`，保留 requestId/traceId/operationId 和脱敏 string-only context。禁止自造 `{error: ...}`、把第三方错误/用户输入/堆栈放进 code 或用户提示。
- 四环境服务配置只来自服务 `config/schema.yaml` 与 `environments/<env>/config.yaml`；稳定资源属于 `resources/`，环境资源只保存 seed/release/artifact 引用。
- 第一方业务对象只由 canonical immutable release importer 激活；fixture、UAT 支持、启动器或基础设施 canary 不得直写业务存储或进入公开投影。
- 第一方部署基线归服务 `deploy/base`，环境入口属于 `environments/<env>/deploy`；跨服务装配、发布与巡检只经 `environment-ops`/`stackctl`。

## 测试与证据

- 对象测试位于 `tests/<layer>/<context>/<object>/`，共享启动器只在 `tests/support`。对象生产实现不用旁路同包测试；`runtime/`、`internal/`、`tools/`、`cmd/` 与服务 `cmd/**` 的合法白盒测试以 `__local_contract_test.go` 结尾。`api_integration` 始终进 canonical 测试树。
- `local_contract` 只用对象级 typed builder/generator、固定 clock/ID 与最小 wire/golden；`api_integration` 通过 application command/provider state 构造前置。直接 storage 只用于 persistence adapter、migration 和 corruption recovery 专项。
- 新 API/event/field/error、consumer/importer/recommendation projection/background task 要同步评估 App codegen/Remote，并声明 metric、trace/request identity、日志脱敏、SLO、告警、配置来源和回滚。
- `local_contract`、`api_integration`、`user_acceptance`、环境/readback 分层报告。契约图 PASS 不代表 API/runtime/App/UAT 通过。

## 验证入口

- metadata 变更：`make verify-metadata`；服务目录/配置/资源/部署变更：`make verify-service-architecture`。
- 生成：`make codegen` 与必要的 `make codegen-app`；结构化错误边界：`dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`。
- 再执行 owner manifest/Review plan 列出的聚焦 Go/local-contract/api-integration evidence。不裸跑不同 profile 的 contract validator 并把其输出冒充 canonical gate。
- 环境、部署或拓扑改动使用 `python3 quwoquan_ops/cli/stackctl.py package/verify/health/inspect`。

# assistant 元数据承接说明

`contracts/metadata/assistant/` 是个人助理端云一体化的唯一元数据真相源。

当前阶段只生成端侧 Dart 产物并做端侧校验，但目录和 schema 必须从一开始就按端云协同设计，避免后续 assistant-service 落地时再次拆目录或搬迁契约。

## 目录原则

- 按业务对象分目录，而不是按技术层或端侧模块分目录。
- 可被 Dart 与 Go 同时消费的契约，直接放在 `assistant/` 下的对象目录中。
- 只属于云侧存储/事件/API 的对象，仍放在 `assistant/` 下，但使用 `aggregate.yaml`、`fields.yaml`、`storage.yaml`、`events.yaml`、`service.yaml` 这些服务元数据文件承接。
- 真正跨多个 assistant 对象复用、且不属于任何单一业务对象的值域，才允许放入 `_shared/`。

## 当前对象分层

### 共享契约对象

以下对象同时服务于端侧 runtime、未来 assistant-service、以及端云协同协议：

- `_shared/enums.yaml`
- `assistant_turn/schema.yaml`
- `intent_graph/schema.yaml`
- `run_artifacts/schema.yaml`
- `query_task/schema.yaml`
- `subagent_plan/schema.yaml`
- `preference_fact/schema.yaml`
- `recall_result/schema.yaml`

这些 schema 的约束：

- 字段、枚举、wire name、默认值以 metadata 为准。
- Dart 端只能消费 codegen 产物，禁止回写 generated 目录。
- 后续 Go 端新增生成目标时，必须复用同一份 schema，禁止复制一套 assistant 专用 DTO 定义。

### 云侧业务对象

以下对象是 assistant-service 的业务承接位：

- `assistant_run/`
- `skill_consent/`

它们负责承接云侧存储、事件、服务接口和治理策略，不应该与上面的共享协议对象混放到 app 目录或 runtime 目录里。

## codegen 目标

当前已落地：

- Dart: `quwoquan_app/lib/personal_assistant/runtime/generated/`

后续扩展时必须新增而不是迁移现有 schema：

- Go domain/application/adapters 所需 DTO / enum / parser
- Go handler / contract test / event 适配代码
- 端云协同协议转换层

## assistant-service 承接约束

- `services/assistant-service/` 未来必须通过 `/qwq-extend new-service` 创建，禁止手动建服务目录。
- 服务目录必须遵循仓库根规则中的 DDD 分层与 runtime 统一能力约束。
- `assistant_turn`、`intent_graph`、`run_artifacts` 属于共享协议，不应在 `services/assistant-service/internal/` 中手写第二套字段定义。
- assistant-service 若需要扩展字段，必须先改 metadata，再做 Go/Dart 双端 codegen。

## 演进顺序

1. 先继续补齐 assistant 共享 schema 与 codegen。
2. 再为 Go 代码生成补充目标模板与输出目录。
3. assistant-service 创建后，只消费 metadata/codegen 产物，不回写 schema。
4. 端侧 runtime 与云侧 service 共享同一 wire contract，端侧只保留隐私/本地数据相关缩小能力。

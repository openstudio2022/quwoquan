# 跨服务契约基础设施

本目录只保存跨服务 schema、共享协议和值定义，不保存任何领域对象根、服务注册、源码路径、测试路径或 readiness。领域对象唯一真相源位于所属服务：

```text
quwoquan_service/services/<service>/contracts/
├── domain.yaml
├── _shared/                         # 仅服务内跨对象共享，按需存在
└── <bounded-context>/
    ├── context.yaml
    └── <business-object>/
        ├── object.yaml
        ├── fields.yaml
        ├── operations.yaml
        ├── storage.yaml
        ├── events.yaml
        ├── errors.yaml
        ├── behaviors.yaml
        ├── privacy.yaml
        ├── ui_config.yaml
        └── projections/
```

控制面对象采用同一规则，位于 `quwoquan_service/control-plane/<control-plane>/contracts/`。

## 路径身份

源码路径 `services/<service>/internal/<context>/<object>/<layer>` 唯一反推：

- service：服务目录名；
- metadata domain：该服务 `contracts/domain.yaml`；
- bounded context：源码路径中的 context；
- business object：源码路径中的 object；
- object kind：同服务 `contracts/<context>/<object>/object.yaml.kind`；
- DDD layer：源码路径中的 layer。

文件内禁止重复 domain、context、object、service、源码路径、测试路径、DDD layer 或 readiness。

声明 `operations.yaml.api_routes` 的对象必须拥有同路径源码根；HTTP adapter、用例、领域规则和
持久化实现不得借住同服务的“主对象”目录。没有公开 route 的投影、内部事实或 external
reference 可以只保留契约/生成物，其数量与 kind 分布均由扫描派生，不用空目录占位。
对象的 adapters/infrastructure 是私有实现，兄弟对象只能依赖其 domain/application port
或事件；多对象 adapter 在 cmd 组合。测试文件同样使用自身 context/object 路径，共享测试
启动支持只进入 tests/support。
服务一旦生成 errors，必须让每个对象 errors.yaml 与 generated/<context>/<object>/errors.*
一一对应；domain wildcard 和把多对象错误聚合进主对象包都属于第二真相源。
跨服务公共契约的派生客户端可放在实际消费对象 generated 路径，但必须在生成 header 中
精确指向存在的外部对象契约，且不得成为可编辑的第二真相源。

## 基础设施内容

```text
contracts/metadata/
├── _schemas/       # context/object/fields/operations/storage/events 等严格 schema
├── _shared/        # 真正跨服务、无单一对象 owner 的协议和值定义
├── _vectors/       # 跨服务向量协议
└── DESIGN.md       # ContractGraph/compiler 设计
```

对象独立 kind 仅允许 `aggregate_root`、`append_only_fact`、`projection`、`external_reference`、`runtime_session`；`owned_entity` 和 `value_object` 只作为聚合成员。

服务根固定目录为 `contracts/`、`internal/`、`generated/`、`cmd/`、`config/`、
`resources/`（按需）、`deploy/`、`environments/`、`tests/`、`build/`，以及仅在确有
服务级 SLI/SLO 时存在的 `observability/`。不得在服务根保存 README 镜像、嵌套
`.qwq_output`、环境外置配置或人工对象/codegen 清单。

## 编译视图

旧式 domain/context/object 树不再提交。现有 compiler 通过以下命令从服务契约构建可删除视图：

```bash
python3 scripts/contracts/build_service_contract_view.py
```

视图仅位于 `.qwq_output/env/repo/local/service-contract-view/cache-*`，每个 Make 或验证进程独占一个可删除目录。不得被业务代码、运行服务或下一次构建当作唯一输入。

## 验证

```bash
make verify-metadata
make codegen
make verify-service-architecture
```

生成代码统一输出到服务根 `generated/<context>/<object>`，禁止手改或写入 `internal`。

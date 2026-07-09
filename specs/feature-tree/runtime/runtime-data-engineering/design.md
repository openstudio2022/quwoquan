# L2 设计：runtime-data-engineering

## 设计目标

运行时数据工程以“发布物可校验、引用可追踪、环境可隔离”为目标，为内容、推荐、小艺和对象主页网络提供同源数据输入。

## 设计原则

- metadata-first：字段、路由、错误码和读模型仍由 metadata 管理，数据工程只提供事实输入。
- seed-first：alpha/beta/gamma 的测试数据必须来自 contract fixture 与 seed manifest。
- single-source：标签、实体归一、对象关系边只能有一个发布源。

## 数据流

```text
原始数据/运营导入/内容反抽
  -> 数据工程清洗与归一
  -> publish/tags + canonical entity + relation edge
  -> metadata/codegen + 服务端投影 + App Mock/Remote
  -> 行为回流与推荐/小艺学习
```

## 输出根边界

- 仓内（版本控制）：输入契约（`tasks/**/task.yaml`、defaults、schema、templates）与唯一入库
  生成输出 `publish/**`（含 `publish/creators/**` 池成品，跨批次引用复用）。
- 仓外（`QWQ_OUTPUT_ROOT`，gitignore 隔离、可清理重建）：
  `runtime/{e2e|operations}/{contentType}/{supplyMode}/…` 批次树、`runtime/site_supply`、
  `runtime/{creator_pools,user_pools}`、`runtime/tasks` snapshot、`artifacts/**` 摘要索引（index-first
  回指 runtimeBatchRoot/taskId/publishRoot/releaseId 与批次三轴）、`release/**`。
- 过程产物不得反向回写可复用层；唯一通道是 approved 对象经 promote/ship 进入 `publish/**`。
- 门禁：`verify_output_root_isolation.py` + `verify_directory_evidence_chain.py`（证据面门）随
  `verify_quwoquan_data.sh` 进 `make gate`。

## 与对象主页网络的关系

`object-homepage-network` 需要数据工程提供：

- `tagRef`：解释交集与内容分类。
- `canonicalEntityId`：统一离线实体和运行时共享主页。
- `entityRef`：内容、评论、圈子与实体的引用关系。
- `relationEdge`：构成 ObjectRelationEdge 的候选事实。

## 校验策略

- local_contract：schema、路径、tagRef、实体引用、seed manifest 静态校验。
- local_contract：App Mock 与 contract fixture 同构测试。
- api_integration：local-gamma 使用 RemoteRepository 读取云侧 seed。
- user_acceptance：对象主页和推荐旅程验证数据闭环。

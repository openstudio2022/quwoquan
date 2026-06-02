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
  -> publish/v1/tags + canonical entity + relation edge
  -> metadata/codegen + 服务端投影 + App Mock/Remote
  -> 行为回流与推荐/小艺学习
```

## 与对象主页网络的关系

`object-homepage-network` 需要数据工程提供：

- `tagRef`：解释交集与内容分类。
- `canonicalEntityId`：统一离线实体和运行时共享主页。
- `entityRef`：内容、评论、圈子与实体的引用关系。
- `relationEdge`：构成 ObjectRelationEdge 的候选事实。

## 校验策略

- T1：schema、路径、tagRef、实体引用、seed manifest 静态校验。
- T2：App Mock 与 contract fixture 同构测试。
- T3：local-gamma 使用 RemoteRepository 读取云侧 seed。
- T4：对象主页和推荐旅程验证数据闭环。

# L2 规格：runtime-data-engineering

## 定位

`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。

本能力当前重点承接：

- `tagRef` 路径制标签发布物。
- 地理与内容三元组。
- 规范实体归一。
- 面向对象主页网络的关系边、实体引用和 seed manifest。

## 范围

负责：

- 定义数据工程发布物的目录、schema、校验和门禁。
- 保证 alpha/beta/gamma/prod 使用同一数据真相源。
- 为 metadata、推荐、小艺和对象主页网络提供 `tagRef/entityRef/canonicalEntityId/relationEdge` 输入。

不负责：

- 替代业务服务的在线写路径。
- 在端侧或 UI 层创建第二套 mock 数据。
- 直接决定推荐排序或小艺触发策略。

## 约束

- 标签真相源为数据工程 `publish/tags`，不得恢复扁平枚举。
- 实体归一产物必须能映射到运行时 `canonicalEntityId`。
- seed manifest 必须区分 alpha、beta、gamma、prod 数据策略。
- 新增数据发布物必须有 local_contract 校验脚本或 contract fixture。

## 验收重点

- 数据工程产物可被 metadata/codegen/服务端/端侧共同引用。
- 对象主页网络所需 `tagRef/entityRef/canonicalEntityId/relationEdge` 有明确输入边界。
- 门禁可阻止第二真相源和环境数据漂移。

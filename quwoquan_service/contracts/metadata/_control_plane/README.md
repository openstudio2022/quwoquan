# `_control_plane` 草稿区说明

本目录用于承载统一控制面的样例级、领域级草稿，当前不是最终的全局唯一真相源。

## 与 `_shared` 的关系

- `_shared/portal_shell.yaml`
- `_shared/portal_menu.yaml`
- `_shared/control_plane.yaml`
- `_shared/config_schema.yaml`
- `_shared/workflow.yaml`
- `_shared/audit_schema.yaml`

以上文件承载的是“全局公共基线”：
- 门户壳层的通用能力
- 菜单与对象模型的最小集合
- plane / risk / approval / rollout 的公共语义
- `sys.*` 配置 schema 的公共字段
- workflow / audit 的公共字段与最小模型

本目录承载的是“更接近产品落地页面与对象”的样例草稿：
- 根目录的 `portal_shell.yaml`、`portal_menu.yaml`：统一门户的样例化编排
- `platform/`：`platform-control-plane` 的领域对象与操作样例
- `product/`：`product-control-plane` 的领域对象、workflow、audit、config 样例

## 当前整理结论

当前不将本目录内容直接整体并入 `_shared`，原因如下：
- 根目录门户草稿混入了 `product-ops` 的对象与工作台语义，不适合作为平台公共基线
- `platform/` 与 `product/` 下的文件已经进入“对象/操作样例”层，不再是纯 schema 层
- 若直接合并，会形成 `_shared` 与 `_control_plane` 双份定义，破坏 metadata 单一真相源

## 后续并入原则

只有满足以下条件时，才允许将本目录内容上收进入正式基线：
- 内容可抽象为跨域公共语义，而不是某个控制面的具体业务对象
- 字段、枚举、命名与 codegen 目标已冻结
- 不依赖某个具体门户页面、路由实现或当前部署拓扑
- 对应 `spec.md / design.md / acceptance.yaml` 已明确引用和验收

## 当前建议

- 将 `_shared` 作为后续 codegen 的正式输入基线
- 将 `_control_plane` 作为 `platform-ops` / `product-ops` 下一阶段 `/dev` 的样例输入区
- 后续按“公共字段上收、领域对象下沉”的原则逐步收敛：
  - 公共字段、公共枚举、公共审批与审计规则 -> `_shared`
  - 领域对象、具体操作、具体 workflow、具体 dashboard 编排 -> 对应控制面目录

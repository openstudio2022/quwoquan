# architect · design · base

## PRE 准入

- [MUST] 对象边界已完成 `owned_entity` vs `separate_aggregate` 裁决，并写入对应 spec/design
  check: 读目标 L1/L2 `design.md` 的 DEC 段；找不到该对象的边界裁决结论，或裁决只写了结果没写依据，判失败
- [MUST] command / query 分流已裁决：写路径与读路径各自的 typed port 已命名
  check: 读设计文档；若页面或 Provider 计划依赖聚合 Repository、或依赖运行时数据源切换，判失败
- [MUST] 新增或改动的字段、错误码、path、operation、surface 已先落到所属服务 `contracts/**`
  gate: make verify-metadata
- [SHOULD] 跨对象依赖只经对方 domain/application port 或领域事件，不直连对方 infrastructure
- [SHOULD] DDD 依赖方向为 `adapters/inbound → application → domain`，infrastructure 只实现 port

## DURING 执行中

- [MUST NOT] 引入第二真相源：同一字段、错误码或值定义在契约之外再写一份
  check: 对每个新增字段/错误码，在 `contracts/**` 之外搜同名定义；实现或测试里存在第二处
  定义（而非引用 codegen 产物），判失败
- [MUST NOT] 引入契约多轨：版本信封、wire 多键双读、dual-read/dual-write、长期 shim、
  compat/warn-only 逃逸，或为错误实现加 fallback
  check: 读 decoder 与 adapter 变更；同一语义存在两个 wire key、或失败路径回落到兼容分支，判失败
- [MUST NOT] 手改 codegen 产物
  check: 重跑 `make codegen` 与 `make codegen-app` 后 `git diff --stat` 必须为空；
  生成物出现 codegen 无法复现的改动，判失败

## POST 自检

- [MUST] 领域治理与 DDD/CQRS 基线通过
  gate: make verify-domain-governance
- [MUST] 服务 DDD/CQRS 基线通过
  gate: make verify-service-ddd-cqrs-baseline
- [MUST] 契约与 metadata 一致
  gate: make verify-metadata
- [SHOULD] 特性树链接与章节完整
  gate: make verify-feature-tree

## HANDOFF 交接

- 产出：DEC 编号、对象边界裁决结论、受影响 `contracts/**` 路径清单
- 未决项去向：边界存疑的对象转最低可关闭节点 `OPEN-###`，不要留在设计讨论里
- 下一步：`dev`，其对象扩展 PRE 需要本次的边界裁决结论与 typed port 命名
- 证据链：上述 gate 的实际输出

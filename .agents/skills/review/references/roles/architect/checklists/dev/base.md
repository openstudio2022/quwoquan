# architect · dev · base

## PRE 准入

- [MUST] 本次实现落在已裁决的对象边界内；越界就回 `design` 重新裁决
  check: 对照 design HANDOFF 或 dev 对象扩展裁决；改动触及未裁决对象，判失败
- [MUST] 契约先行已完成：先改 `contracts/**` → verify/codegen → 再写业务逻辑
  check: 若业务代码引用了尚未进契约的字段或错误码，判失败

### 对象扩展追加：对象边界五问（仅对象级扩展时适用）

- [MUST] 这个东西是不是一个独立对象？还是某个已有对象的属性或值对象？
  check: 读目标 L1 `design.md`；若新增对象没有自己的生命周期与标识，却被建成独立聚合，判失败
- [MUST] 它归谁所有？`owned_entity`（随宿主生灭）还是 `separate_aggregate`（独立生灭）？
  check: 裁决结论必须显式写出并给依据；只写结论不写依据判失败
- [MUST] 谁能改它？写入口是哪个 `*CommandWriter`，唯一吗？
  check: 存在两个以上写入口、或写入口未命名，判失败
- [MUST] 谁要读它？读出口是哪个 `*Query`，返回的是投影还是聚合本体？
  check: 页面或 Provider 直接读聚合本体而非投影，判失败
- [MUST] 跨对象怎么依赖？经对方 domain/application port 还是领域事件？
  check: 出现直连对方 infrastructure 或共享数据库表，判失败

## DURING 执行中

- [MUST NOT] 手改 codegen 产物
  check: 重跑 `make codegen` 与 `make codegen-app` 后 `git diff --stat` 必须为空；
  生成物出现 codegen 无法复现的改动，判失败
- [MUST NOT] 新增或扩大 mock/fixture/test-only allowlist
  check: 对比改动前后的 allowlist 与棘轮基线；条目数或上限变大，判失败（只减不增）

## POST 自检

- [MUST] 契约与 metadata 一致
  gate: make verify-metadata
- [SHOULD] 纵向架构棘轮未退化
  gate: make verify-vertical-architecture-ratchet

## HANDOFF 交接

- 产出：改动的 `contracts/**` 与实现路径、codegen 重跑范围；对象扩展附五问逐条答案与
  typed port 清单
- 未决项去向：绕过契约的临时实现与边界未定对象必须转 `OPEN-###`
- 下一步：POST 评审汇总，其 PRE 需要本次的契约 diff 范围
- 证据链：上述 gate 的实际输出

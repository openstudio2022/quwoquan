# test · dev · service

适用：改动触及 `quwoquan_service/**`，尤其对象级扩展。层次放错是这里最常见的失败：
该进 `api_integration` 的用 in-memory double 糊过去，该进 `local_contract` 的跑去连真实存储。

## PRE 准入

- [MUST] 新增或改动的每个 typed port 都已确定证据层
  check: 逐个 port 指出它由哪一层覆盖；指不出，判失败
- [MUST] `add-query` 类扩展已明确 typed Slice 的断言方式
  check: 只断言「返回非空」而不断言字段、顺序、分页与空态，判失败
- [SHOULD] 已确认反序列化的必填缺失路径有 fail-closed 用例

## DURING 执行中

- [MUST NOT] 用 in-memory double 替代 `api_integration` 对真实读写存储的验证
  gate: make verify-api-integration-direct-storage
- [MUST NOT] 让对象级 typed double 逸出测试树，进入 runner、UAT support 或环境 App
  gate: make verify-app-mock-isolation
- [MUST NOT] 用动态 skip 掩盖尚未就绪的环境依赖；缺依赖如实报阻塞
  gate: make verify-test-no-fake

## POST 自检

- [MUST] 对象证据闭包成立
  gate: make verify-object-evidence-closure
- [MUST] 三层映射与覆盖成立
  gate: make verify-test-coverage-map

## HANDOFF 交接

- 产出：新增测试文件路径与其覆盖的 port、三层归属表
- 未决项去向：暂缺环境依赖而无法覆盖的层转 `OPEN-###`，写明缺什么才能补齐
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出

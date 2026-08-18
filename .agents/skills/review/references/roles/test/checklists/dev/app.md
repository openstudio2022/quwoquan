# test · dev · app

适用：改动触及 `quwoquan_app/**` 的测试或被测代码。

## DURING 执行中

- [MUST NOT] `local_contract` 使用聚合 mock package 或可被环境 App 引用的 mock
  gate: make verify-app-mock-isolation
- [MUST NOT] 测试 double 进入任何环境 App 的可达图
  gate: make verify-production-wiring-purity
- [MUST NOT] 环境测试书写 capability 字符串、裸字典参数、固定业务对象 ID 或导入 Provider 实现
  gate: make verify-test-data-architecture
- [MUST NOT] 关闭关键像素/视觉断言换取稳定性；`toImage()` 慢只能缩小画布、
  减少采样点或拆单帧测试
  check: 对比改动前后的视觉测试；像素断言被删除或降级为非像素断言，判失败

## POST 自检

- [MUST] Mock 隔离通过
  gate: make verify-app-mock-isolation
- [SHOULD] 测试数据架构合规
  gate: make verify-test-data-architecture

## HANDOFF 交接

- 产出：App 侧测试改动清单
- 未决项去向：未覆盖项转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出

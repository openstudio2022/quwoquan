# 测试侧 Cloud 替身

本目录只保存 production `lib/**` 不可达的测试适配与统一 re-export。测试通过 [`repository_mock_reexports.dart`](repository_mock_reexports.dart) 引用替身，不从业务代码导入 Mock。

- assistant：local_contract 使用对象级强类型 fixture 与 provider override；这些 helper 不得被 runner 或 UAT support 引用。
- chat：状态和 fixture 解析必须迁移到测试树内最小 typed double；测试 mapper 与 parity gate 只证明 local_contract，不得成为 Alpha 环境数据源。

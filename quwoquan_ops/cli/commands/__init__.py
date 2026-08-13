"""stackctl 子命令域包。

`quwoquan_ops/cli/stackctl.py` 仍是唯一环境操作入口：它负责 bootstrap、
`build_parser()` 组合与 `main()` dispatch。本包按子命令域拆分 argparse
表面与编排胶水，每个域模块提供 `register_parser(subparsers)` 与
`command_*` 实现（参照 travel_to_gathering_migration 的外挂模式），
业务逻辑保持在 `quwoquan_ops/cli/lib/**`。

约束：
- 子命令名、参数、帮助文案、输出文本与错误码对 stackctl.py 零漂移。
- 域模块内可被测试 monkeypatch 的符号一律经函数内延迟导入的
  ``import quwoquan_ops.cli.stackctl as _stackctl`` 属性访问，既避免
  顶层循环 import，也保持 ``mock.patch.object(stackctl, ...)`` 语义。
"""

"""finalize_mainline_release_artifact 的实现子包。

原单文件 CLI 已按职责拆分为：

- ``canonical_digests``：规范字节序列化、candidate/manifest 摘要与快照封存。
- ``manifest_validation``：manifest 结构、生命周期状态与收据描述符校验。
- ``evidence_files``：镜像/应用包描述符加载与文件级证据摘要复核。
- ``finalize_flow``：CLI 参数解析、收据落盘与生命周期推进主流程。

契约常量（SCHEMA、FORBIDDEN_FIELDS 等）由入口模块
``quwoquan_ops.cli.prod.finalize_mainline_release_artifact`` 定义并被门禁
AST/文本扫描钉住；本包子模块反向从入口 import 这些常量。因此**只允许经
入口模块间接使用本包**，禁止其他消费者直接 import 子模块（否则会在入口
初始化中途触发循环导入）。
"""

# assistant-service Agent Guide

本目录是 metadata domain \`assistant\` 的自治服务边界；同时遵守仓库根和 \`quwoquan_service/AGENTS.md\`。

- 先修改 \`contracts/\`，再执行契约校验/codegen；禁止手改 \`generated/\`。
- 人工源码只放 \`internal/<context>/<object>/<layer>\`；不得恢复 domain 重复层。
- \`config/schema.yaml\`、\`resources/\`、\`deploy/base\` 是共享基线；四环境差异只放 \`environments/<env>\`。
- 环境间禁止继承；secret 只保存 reference；Alpha/Beta/Gamma 外部 Provider 只允许 typed Port 对等本地替身；Gamma 必须运行完整第一方拓扑与 production Remote composition；Prod 才绑定真实 Provider，真实凭据只允许仓外注入。
- 服务不得导入其他服务的 \`internal\` 或 \`generated\`；跨服务协作只走契约和端口。
- 测试归 \`tests/local_contract/<context>/<object>\` 或 \`tests/api_integration/<context>/<object>\`。

# assistant-service Agent Guide

本目录是 metadata domain \`assistant\` 的自治服务边界；同时遵守仓库根和 \`quwoquan_service/AGENTS.md\`。

- 先修改 \`contracts/\`，再执行契约校验/codegen；禁止手改 \`generated/\`。
- 人工源码只放 \`internal/<context>/<object>/<layer>\`；不得恢复 domain 重复层。
- \`config/schema.yaml\`、\`resources/\`、\`deploy/base\` 是共享基线；四环境差异只放 \`environments/<env>\`。
- 官方 Skill 受控源码唯一根是 \`resources/skill_packages/official\`；它只供 publisher/测试的 SourceBuilder 使用。生产运行只消费 \`resources/skills/packages/official\`（或环境注入的同构根）下签名且已激活的 immutable release，禁止源码扫描 fallback、软链接或双根。
- Skill 路由可消费 active package 内部能力，但只有 \`CatalogProfile.visibility=listed\` 且 Catalog/Input/Context/Capability/Presentation/Evaluation/Replay 均完整、相互引用可验证的 Skill 才能进入用户目录；展示分组、目标人群、权限说明、surface 与示例均来自 digest 固定的 package 语义资产，App 不得按 skillId/domainId/scope 手写垂类映射。
- AgentLoop 只按 canonical Tool metadata 的能力、研究语义、预算和恢复合同决策；不得按 toolName、SkillID、domainId 或具体 Provider 写搜索、导航、确认、重试和降级分支。新增同类 Tool 只允许增加 metadata 与 adapter。
- 环境间禁止继承；secret 只保存 reference；Alpha/Beta/Gamma required 验收能力绑定受管非生产租户的非内存 Provider，缺凭据或 conformance 即 `GATE_BLOCK`；Prod 仅绑定正式生产租户。所有凭据只允许仓外注入。
- 服务不得导入其他服务的 \`internal\` 或 \`generated\`；跨服务协作只走契约和端口。
- 测试归 \`tests/local_contract/<context>/<object>\` 或 \`tests/api_integration/<context>/<object>\`。

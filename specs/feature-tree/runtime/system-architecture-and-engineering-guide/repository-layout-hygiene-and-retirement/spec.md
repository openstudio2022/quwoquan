# L3 特性：repository-layout-hygiene-and-retirement

## 目标

建立可重复、可证据化的全仓目录整洁机制，确保源码树只保留可追溯的源码、
契约、生成物、供应链依赖和运行资产；可再生产缓存、构建产物、失效入口和
历史副本必须能被识别、分批清理并由门禁阻断回归。

## 范围

- Git 跟踪、未跟踪和 ignored 路径的只读 inventory：状态、大小、SHA-256
  （对超过哈希预算的文件明确记录未计算原因）、分类、WIP 排除和引用证据。
- 可再生产输出的统一边界：`.qwq_output/`、Flutter/Gradle/Node/Python
  缓存和构建目录不进入源码树；运行中的证据与用户 WIP 不被自动清理。
- 已证实残留的原子退役：跟踪的 Service 测试二进制、失效 mock-test 根检查、
  未注册 Data audit 入口、重复发布计划副本和重复 Service 配置脚本。
- 唯一入口收敛：Data 业务验证经 `python3 quwoquan_data/scripts/cli.py verify all`，
  stackctl 使用 `--profile`，推荐模型训练使用 service-owned scripts 路径，
  设备修复脚本位于 `quwoquan_app/scripts/device/`。
- Service/App/Data/Ops layout gate 对根级二进制、活动入口、输出根隔离和目录
  双向引用提供可定位的失败信息。
- 活动 Make/Actions/gate 中的仓内脚本路径与第一方 Markdown 相对链接由静态门禁阻断断链。
- 特性树只保留全局 `tree_index.yaml`，L1 `tree.yaml` 镜像不得回流；全部 CR YAML
  必须可被标准解析器读取。
- Fixture 媒体按 metadata、环境清单和活动源码引用建立正反向闭包；旧无 slice 路径、
  未引用 archived 副本和同哈希原始别名不得回流。
- App 打包资产使用精确文件声明；已清零的语义债务不再保留空 baseline 或可重新放宽
  的更新入口，棘轮 allowlist 必须与当前命中精确一致。

## 分类契约

审计报告只允许使用以下分类：

| 分类 | 处理语义 |
|---|---|
| `protected_wip` | 当前 Git 修改、删除或未跟踪路径，硬排除，不自动删除 |
| `managed_generated` | 由 codegen/manifest 管理，回到生成器维护 |
| `vendored_dependency` | vendor 或外部供应链资产，保留许可证和来源 |
| `runtime_or_fixture_asset` | metadata、schema、fixture、控制面和长期运行参考资产 |
| `retained_operational_or_lane_dependency` | 已核实仍有活动调用方或外部运维责任的保留项 |
| `reproducible_local_output` | 可由依赖、构建或 stackctl 重建的缓存/输出 |
| `reachable_source` | 当前入口或契约可达的源码、测试和配置 |
| `review_required_candidate` | 需核对外部手工调用、保留期或迁移责任 |
| `high_confidence_retire` | 已完成引用、状态和最小验证，允许原子退役 |

`protected_wip` 优先级高于其他分类；未跟踪 `.env`、IDE 设置、证书、密钥和
运行中环境文件不得因为文件名看似可清理而被删除。

## 真相源与验证

- 审计入口：`quwoquan_ops/cli/repo_hygiene_audit.py`。
- 输出根：`QWQ_OUTPUT_ROOT/env/repo/runs/`；报告可删除，不是工程真相源。
- App、Service、Data 的业务入口和生成 manifest 仍分别以现有 `Makefile`、
  `pubspec`/generated manifest、Service ContractGraph、Data CLI 和 feature tree
  为准，本 Story 不复制这些清单。
- 最小验证：`python3 quwoquan_data/scripts/cli.py verify all`、
  `python3 quwoquan_service/scripts/verify/verify_service_layout.py`、
  `python3 quwoquan_ops/gate/verify_output_layout.py`、
  `python3 quwoquan_ops/gate/verify_entrypoint_script_paths.py`、
  `python3 quwoquan_ops/gate/verify_markdown_local_links.py` 和
  `python3 quwoquan_ops/gate/verify_alpha_media_fixture_surface.py --files-only`、
  `python3 quwoquan_ops/cli/repo_hygiene_audit.py`。

## 非范围

- 不删除当前 WIP、`.env`、IDE 用户设置、证书/密钥、商业 SDK、`vendor/plugins/**`、
  已被正式 fixture/环境/App 消费的媒体对象或仍可能由外部运维使用的备份脚本。
- 不把审计报告、运行输出或清理候选清单升级为第二套契约、拓扑、metadata、
  feature tree 或 backlog 真相源。

# Environment Test Layout Inventory

## 目标

端侧测试入口统一放在 `quwoquan_app/test/` 下，按 `common`、`alpha`、`beta`、`gamma` 与 `patrol` 分层。`integration_test/` 不再作为测试分层概念保留。

## 迁移结果

| 原路径 | 新路径 / 处理 | 状态 |
|---|---|---|
| `quwoquan_app/integration_test/assistant_alpha_beta_simulator_test.dart` | `quwoquan_app/test/gamma/assistant_alpha_beta_simulator_test.dart` | 已迁移 |
| `quwoquan_app/integration_test/assistant_eval_scenario_fixtures.dart` | `quwoquan_app/test/common/assistant/assistant_eval_scenario_fixtures.dart` | 已迁移 |
| `quwoquan_app/integration_test/assistant_skill_comparison_test.dart` | `quwoquan_app/test/gamma/assistant_skill_comparison_test.dart` | 已迁移 |
| `quwoquan_app/integration_test/assistant_answer_protocol_leak_regression_test.dart` | `quwoquan_app/test/common/assistant/protocol/assistant_answer_protocol_leak_regression_test.dart` | 已迁移 |
| `quwoquan_app/integration_test/assistant_skill_matrix_validation_test.dart` | `quwoquan_app/test/common/assistant/skills/assistant_skill_matrix_validation_test.dart` | 已迁移 |
| `quwoquan_app/integration_test/pageflip_diagnostics_visual_test.dart` | `quwoquan_app/test/common/pageflip/pageflip_diagnostics_visual_test.dart` | 已迁移 |
| `quwoquan_app/integration_test/patrol_test_main.dart` | `quwoquan_app/test/patrol/patrol_test_main.dart` | 已迁移 |
| `quwoquan_app/integration_test/assistant_manual_replay_test.dart` | 由 `assistant_scenarios.json` 的 stock/weather/travel 场景承接 | 已删除 |
| `quwoquan_app/integration_test/support/assistant_replay_baseline.dart` | 旧 replay baseline 私有支撑 | 已删除 |
| `quwoquan_app/integration_test/assistant_native_weather_query_test.dart` | 由环境 smoke + contracts scenario 覆盖，不保留天气业务旧入口 | 已删除 |

## 规则

- 新增端侧环境测试只能放在 `quwoquan_app/test/common`、`test/alpha`、`test/beta`、`test/gamma` 或 `test/patrol`。
- 是否跑设备/模拟器由 runner 的 `-d <device>` 参数决定，不通过目录名表达。
- alpha/beta/gamma 的业务对象和断言数据必须来自 `contracts/metadata/**/test_fixtures`。
- `quwoquan_app/pubspec.yaml` 不得挂载 contracts `test_fixtures` 为生产 assets。
- `app-alpha` 可随包携带 seed manifest allowlist 中的精简 fixture；`app-beta/app-gamma` 只能通过 remote/gateway 读取云侧 seed 数据。
- App 只构建 `alpha/beta/gamma/prod` 四类环境包；不存在独立 `app-prod-gray` 包。
- 人工 beta 数据必须来自 `app_beta_seed_manifest.json`，不得在启动脚本或数据库中临时造数。
- 环境包、seed manifest 与 gateway smoke 使用统一命令面：`make build-app-env`、`make verify-app-seed-manifest`、`make test-app-alpha-seed`、`make test-app-beta-seed`。

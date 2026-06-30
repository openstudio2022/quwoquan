# 工作树漂移收口判断（2026-06-30 复核）

用户要求：逐组判断——确属本任务必需产物（四川 task.yaml / 四川三类 fixtures）才精确路径小步提交；脚本副产物 / 无关漂移原样留着不提交不回滚；`quwoquan_app/**` 一律不碰。

## 逐组结论

| 漂移组 | 文件数 | 性质判定 | 处置 |
|---|---|---|---|
| `quwoquan_data/tasks/旅行/.../四川省/景区/规模门/task.yaml` | 1 | **仅 `provenance.createdAt` 时间戳变化**（`task new` 重生成副产物，content/scope/angles 无实质改动） | 留着不提交 |
| `agent_ops/deploy/{gamma,smoke}/run_*_patrol_*.py` + 新增 `agent_ops/deploy/lib/patrol_cli.py` / `agent_ops/tests/test_patrol_cli_resolution.py` | 4 | **Flutter `patrol` 集成测试 CLI 解析基础设施**（环境巡检），与「四川三类内容生产」无关，属环境-ops 他流 | 留着不提交不回滚 |
| `quwoquan_service/contracts/metadata/_shared/`（含 `app_routes.yaml`） | 4 | 端云契约 codegen/seed 重生成副产物，非本任务有意修改 | 留着不提交不回滚 |
| metadata `scenarios`（content/entity/circle/user） | 10 | 同上，他流 scenario 漂移 | 留着不提交不回滚 |
| metadata `ui_config` / `app_routes` / `projections` | 5 | 同上 | 留着不提交不回滚 |
| `artifacts/legal-static-packages/` | 4 | 法务静态包 seed 重生成副产物 | 留着不提交不回滚 |
| `quwoquan_app/**` | 99 | UI 改动（media picker / object_page / profile 等），明确他人任务 | 一律不碰 |

## 验证：metadata 中无四川三类内容 fixture

`git status --short -- quwoquan_service/contracts/metadata/ | grep -iE 'sichuan|四川|景区|九寨|峨眉|都江堰|乐山|游记'` 仅命中 `_shared/app_routes.yaml`（因 grep pattern 含 "route"），**实为 `_shared` 路由元数据，并非内容生产 fixture**。故确认：本任务的四川三类内容产物（task / fixtures / E2E 产物）位于 sandbox runtime（`~/qwq_scale_verify`），不进 repo 工作树；repo 工作树中无任何本任务必需产物待提交。

## 收口结论

- **本任务全部代码与证据产物已提交**（HEAD=`850065496`，链路 70bf7cf4f→e79d9bc79→509d2a2f2→bd42f6557→57b88ba85→86f0e3bdc→850065496）。
- **工作树剩余全部漂移均为他流/脚本副产物 → 一律保留原样，不提交不回滚。**
- 与前窗 `70bf7cf4f` 分诊结论一致；本窗复核无新增本任务必需产物。

# 旅行实体主页家族（homepage-only）

家族契约：只产实体主页（`entityHomepagesPerTarget=1`，article/image 配额为 0），
research 单 homepage lane，禁止 AI 图。默认值真相源 = `base.preset.yaml`。

## 运行

```bash
# 试点（25，trial 口径，不因 no-go 失败）
python3 quwoquan_data/scripts/cli.py task run-recipe content/travel/homepage/pilot

# 百级（100，commercial 口径，no-go 即失败）
python3 quwoquan_data/scripts/cli.py task run-recipe content/travel/homepage/h100

# 千级（1000，commercial 口径；h100 GO 后放量）
python3 quwoquan_data/scripts/cli.py task run-recipe content/travel/homepage/h1000
```

分段执行：`--stage generate-only`（只生成任务并过契约门）、`--stage readiness-only`
（复用既有批次只跑放量验收，配合 `--batch <已有批次>`）。

## 前置条件

- git 分支必须是 `feature/homepage-commercial-lane`（契约门校验，不满足即 BLOCK）。
- `CURSOR_API_KEY` 或 `QWQ_CURSOR_API_KEYFILE` 已配置（`env ready` 预检不通过即退出）。
- 运行环境默认值见 `control_plane/_shared/cursor_local.runtime.yaml`；
  外部环境变量显式声明时优先于 profile。

## 修补

- workflow 未收口：`run-recipe` 内置 author resume 循环（`maxAuthorRounds` 上限），
  中断后用同一 `--batch` 重跑即续跑，不需要单独 resume 脚本。
- 基础设施故障后重试：`qwq-data task retry-stage --task <id> --batch <批次> --stage <阶段>`。

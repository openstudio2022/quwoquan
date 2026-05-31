# L4 细节：environment-ops-cli-and-skill

## 功能说明

定义统一环境运维入口 `stackctl` 的命令面、JSON/Markdown 报告契约、执行后端抽象，以及 Cursor project skill 的集成边界。

## 命令面

- `package`
- `up` / `down` / `status`
- `verify`
- `health`
- `inspect`
- `doctor`
- `repair`
- `deploy`

## 核心约束

- Cursor、CLI、CI、workflow 与 project skill 必须共享同一套 `stackctl` 子命令，不得复制第二套检查/部署逻辑。
- `stackctl` 必须输出稳定 JSON 报告，并在 `artifacts/stackctl/<env>/<run-id>/` 归档 Markdown 摘要。
- `stackctl` 必须支持 `local / ssh-hosted / workflow` 三类执行后端。
- `inspect` 统一覆盖 `logs / network / data / metrics / config / security`。
- `doctor` 只做聚合诊断；`repair` 只能执行白名单修复动作。
- gamma / prod 发布必须通过 `stackctl deploy` 暴露统一入口，底层可复用既有 workflow 与 `config_release_*` 脚本。

## Skill 集成边界

- project skill 只说明何时调用 `stackctl`、如何读取报告与何时停止自动修复。
- skill 不复制业务逻辑，不维护单独的环境枚举、URL 或 host 判定。
- skill 遇到登录、审批、密钥、生产破坏性动作时必须显式停下并请求人工确认。

## 验收标准

- A1：本地、hosted、prod 可通过同一命令面驱动。
- A3：JSON 报告字段稳定，适合 Cursor / CI 机器消费。
- A7：diagnose / repair 边界清晰，不引入隐式破坏性行为。
- A8：CLI 与 skill 的调用契约有自动化 smoke 覆盖。

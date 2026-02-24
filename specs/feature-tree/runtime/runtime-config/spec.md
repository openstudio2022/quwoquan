# L2 特性：runtime-config

## 功能说明
- 提供统一配置运行时能力，支持 env/file/secrets/config-center 多源读取与优先级合并。
- 提供动态刷新、版本快照、灰度发布与回滚审计，保障系统参数可控变更。

## 约束
- 业务服务必须通过 runtime-config 读取 `sys.*` 配置，禁止散落硬编码系统参数。
- 配置变更必须可审计（操作者、范围、旧值/新值、生效时间）。
- 高风险配置（超时/重试/限流/降级/采样）必须支持灰度与回滚。

## 验收标准
- A1：统一 API 可在 8 个服务中注入并读取配置。
- A3：动态刷新与回滚可用，失败可回退到最近稳定快照。
- A7：与 `contracts/configuration.md` 的命名与分层规则一致。
- A8：provider/unit/contract/integration/uat 自动化覆盖完整。

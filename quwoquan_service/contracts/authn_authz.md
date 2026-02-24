# 认证与授权统一规范（AuthN / AuthZ）

目标：统一端侧鉴权、persona 上下文、以及服务间调用鉴权，避免每个服务各自实现导致口径不一致。

---

## 1. 端侧鉴权（AuthN）

- 端侧通过 `Authorization: Bearer <accessToken>` 访问 Gateway。
- Gateway 负责校验 token，并将 `userId`（以及可选 personaId）注入下游上下文（header 或内部 context）。

建议 accessToken（JWT 或等价）最小 claim：
- `sub` / `userId`
- `exp`
- `activePersonaId`（可选：若放在 token 内，则下游可少传 `X-Persona-Id`）
- `roles/scopes`（可选：后期若需要权限分层）

> 具体 claim 命名可调整，但必须在所有服务统一。

---

## 2. Persona 上下文（身份/分身）

二选一（推荐优先 A）：

### A. Persona 内置在 token（推荐）

- 网关解析 token 获取 `activePersonaId` 并透传至下游。
- 端侧切换 persona 后刷新 token（或走短期 session），避免每次请求携带额外 header。

### B. Persona 通过 header 传递（兼容）

- 端侧在需要 persona 的请求中携带 `X-Persona-Id`（见 `contracts/openapi/common.yaml`）。
- 网关校验该 persona 是否属于 userId，并透传给下游。

---

## 3. 服务间调用鉴权（SVC-to-SVC）

目标：Orchestrator/Gateway/Ops 调用业务服务时具备可信身份，避免内网被滥用。

推荐方案：
- **mTLS**（优先）：服务间通过 mTLS 识别对端服务身份（service identity），并在 `runtime/observability` 中记录 `callerService`。
- 备选：内部签名 header / 短期内部 token（需要密钥管理与轮换）。

---

## 4. 授权（AuthZ）

最低可用要求：
- Gateway 层做基础鉴权（是否登录、token 是否有效）。
- 业务服务层做对象级授权（例如：是否有权限删除某评论、是否有权限修改会话设置）。

运营接口要求：
- 面向运营（Ops）调用的“管理接口”必须走独立鉴权路径（例如 admin token / service identity + allowlist），不得复用端侧 accessToken。
  - 运营调用方：`product-ops`

---

## 5. 与公共库的关系（强制）

- token 解析、caller identity、权限校验辅助工具建议统一由 `runtime/` 提供（后续落地）。
- 日志中不得记录 token 明文；debugMessage 需脱敏（见 `contracts/error_codes.md`）。


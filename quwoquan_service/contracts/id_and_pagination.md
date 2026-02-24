# ID 生成与分页统一规范（ID / Cursor Pagination）

目标：统一 ID 生成、排序与 cursor 分页编码，避免各服务实现不一致导致端侧难以复用、联调困难。

---

## 1. ID 生成（建议）

建议优先使用**可按时间排序**的 ID（如 ULID/KSUID）：
- 好处：天然按时间排序，利于 cursor 分页与排障（看到 ID 可大致判断时间）
- 要求：ID 必须全局唯一且不可预测（避免枚举）

若使用数据库自增 ID，必须：
- 不对外暴露可枚举的自增 ID（需再做编码/映射）
- cursor 分页必须使用稳定排序字段（createdAt + id）

---

## 2. Cursor 分页（强制口径）

- 列表接口优先 cursor + limit（见 `contracts/openapi/common.yaml`）。
- 排序必须稳定：建议 `createdAt DESC, id DESC` 或 `createdAt ASC, id ASC`（二者择一并全域统一）。
- cursor 编码建议：base64url(JSON) 或安全编码字符串，至少包含：
  - `sortCreatedAt`
  - `sortId`
  - `direction`

返回结构统一：
- `items: []`
- `nextCursor`（可空）

---

## 3. 与公共库的关系（强制）

- cursor 编解码与校验应由 `runtime/` 提供统一实现（后续落地）。
- 端侧的列表组件可依赖统一结构，避免每页自定义分页协议。


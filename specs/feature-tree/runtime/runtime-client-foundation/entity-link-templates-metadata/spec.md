# L3：实体链接模板元数据（entity-link-templates-metadata）

## 背景与动机

端侧存在 **公网 HTTPS、`quwoquan://` 深链、GoRouter 路径** 多处手写拼接，易与 **`app_routes` / `ui_surfaces`** 漂移；与 **metadata-first** 主线不一致。需要将 **链接结构**（scheme、path 段、query 规则、占位符）与 **对内导航锚点**（`route_id`、`param_bindings`）收拢为 **contracts 唯一真相源**，经 **verify → codegen** 生成端侧（及可选云侧）API，**禁止**在业务组件中重复拼域名与路径。

## 目标用户与目标

| 角色 | 目标 |
|------|------|
| 终端用户 | 复制/分享的链接与 App 内打开路径 **语义一致**；环境切换时仅 origin 变化、路径形态不变 |
| 开发者 | 新增/改链接形态 **只改 metadata + codegen**；Router 与对外 URL **同源映射** |
| 运维 / 增长 | 公网域名通过 **部署或 Remote Config** 配置，**不**改代码、**不**把生产域名写入 Git 内 metadata |

## 功能范围（In Scope）

1. **统一元模型 `link_templates`**（`_shared/link_templates.yaml`）  
   - 覆盖实体：**post、circle、user、chat、entity_homepage**（与当前 `app_routes` 能力对齐）。  
   - 每实体：`app_deep_link`（scheme/host/path_template/query_rules）、`web.path_template`、`navigation.route_id` + `param_bindings`。

2. **权威方与组合规则**  
   - **Canonical 字符串**：客户端按 **metadata 模板 + 运行时 origin** 拼接即可（无需服务端每次返回 URL）。  
   - **HTTPS**：`normalizeOrigin(runtime)` + `web.path_template`（占位符替换 + 编码规则由 design 固定）。  
   - **Scheme**：结构来自 metadata；**scheme 不随环境变化**。

3. **与通用路由的关系**  
   - **显式映射**：`navigation.route_id` **必须**引用 `app_routes.yaml` 已有 `id`；`param_bindings` 声明链接参数 → 路由 path 参数。  
   - 禁止在 Dart 维护第二套「外链 path → 页面」表；Universal Links / App Links 解析应 **回溯到同一 metadata 行**（实现落在后续 slice）。

4. **与姊妹 L3 的关系**  
   - **`metadata-driven-client-data-contract`**：本 L3 是其下 **「可复制链接 / 深链」** 专项，共用 metadata-first 纪律。  
   - **`unified-app-page-access`**：本 L3 的 `route_id` 与 **pageAccess / 路由 codegen** 同源。

## Out of Scope（本 baseline 文档冻结；实现按 plan 切片）

- **codegen 工具改造与全量调用点替换**（沉浸式、分享 sheet、助理 Referer 等）：见 `plan.yaml`，在 **`/dev`** 闭环。  
- **服务端短链、跳转、OG 动态 HTML**：可选后续 story；本 L3 不强制 API 返回 canonical。  
- **iOS AASA / Android assetlinks 文件内容**：运维交付物；metadata 仅提供 **path pattern** 输入。

## 约束

- `route_id` 不在 `app_routes.yaml` 中存在的，**禁止**合入（CI/verify 或 codegen 阶段校验）。  
- metadata **不得**写入生产环境具体域名（仅 `runtime_origin_binding` 声明 **键名** 与来源类型）。  
- 与仓库 **04-fullstack-metadata-consistency**：新增链接形态 **不**在 UI 硬编码 path 字面量作为第二真相源。

## 数据生命周期 / 权限

- 帖子 **private** 等可见性与 **是否允许复制 Web/深链** 仍由现有 **`ContentShareTemplateBuilder` / 分享策略** 等业务规则决定；本 metadata 只提供 **允许复制时的字符串形态**。  
- `query_rules`（如 `scope=circle`）与 visibility 的对应关系在 design 与实现中与现有 `circle_visible` 语义对齐。

## 迁移与回滚

- **迁移**：codegen 产出稳定后，删除/收缩 `AppPublicContentLinks` 内手写 path、`ContentShareTemplateBuilder._deeplinkForPermission` 内硬编码字符串。  
- **回滚**：保留 `link_templates.yaml` 版本字段；回滚代码时 **不删除** metadata，仅恢复调用旧 API。

## L1 / L2 / L3

| 层级 | 标识 |
|------|------|
| L1 | `runtime` |
| L2 | `runtime-client-foundation` |
| L3 | `entity-link-templates-metadata` |

## 验收摘要

见同目录 `acceptance.yaml`；商用与测试矩阵见 `design.md`。

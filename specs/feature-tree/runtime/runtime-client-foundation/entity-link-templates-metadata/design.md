# design：entity-link-templates-metadata

## 1. 上游规格结论

- **Canonical**：客户端 **metadata 模板 + 运行时 origin** 拼接；服务端不强制返回 URL 字符串。  
- **环境**：**scheme 固定**；**HTTPS 主机** 来自 **Remote Config**（目标态）或 **`PUBLIC_WEB_BASE_URL` dart-define**（过渡期），与 `CloudRuntimeConfig.gatewayBaseUrl` **分离**。  
- **实体范围**：Post、Circle、User、Chat、Entity（主页）共用 **同一 YAML schema**（`entities.<key>`）。  
- **路由**：**metadata 显式** `route_id` + `param_bindings`，与 `app_routes.yaml` 对齐，避免外链与 GoRouter 漂移。

## 2. 方案对比

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| A. 仅 dart-define + 手写工具类 | 落地快 | 双真相源、无路由绑定 | **不采用**（当前债） |
| B. metadata 结构 + codegen + runtime origin | 单源、可校验 route、可扩云 | 需改 codegen 与调用点 | **采用** |
| C. 服务端返回 canonical URL | 集中变更 | 弱网/离线、与 App 内 scheme 仍可能双套 | **不作为必选**；可选后续 |

## 3. 元数据模型（`contracts/metadata/_shared/link_templates.yaml`）

### 3.1 顶层

- `version`：契约版本。  
- `runtime_origin_binding`：文档化 **origin 来源**（`dart_define_key` / `remote_config_key`），**不写具体域名**。  
- `entities`：各业务实体一条。

### 3.2 每实体字段

| 字段 | 含义 |
|------|------|
| `primary_params` | 占位符名列表，与 `path_template` 中 `{name}` 一致 |
| `app_deep_link.scheme` / `host` | 固定；组成 `quwoquan://{host}/{path}` 语义（实现时按 Uri 规范组装） |
| `app_deep_link.path_template` | 无前导斜杠或与 Uri 库一致约定（codegen 统一） |
| `app_deep_link.query_rules` | 条件追加 query（如 visibility → `scope=circle`），与现有分享策略对齐 |
| `web.path_template` | **相对 origin** 的路径模板，如 `post/{postId}` |
| `navigation.route_id` | **等于** `app_routes.yaml` 的 `routes[].id` |
| `navigation.param_bindings` | 链接参数名 → 该 route 的 path 参数名（如 `postId` → `id`） |

### 3.3 与 `app_routes` 不一致时的处理

- **公网 SEO 路径** 可与 **App 内 path** 不同（如 web `post/{id}` vs app `/article/{id}`）：**允许**；对内打开以 **`route_id` + bindings** 为准，**不以** web 路径字符串反推路由。  
- Universal Link 若使用 **web 路径**，需在 **后续 slice** 增加 `web_to_route` 解析表或复用本文件 `web` + `navigation`（同一实体一行）。

## 4. Codegen（端侧）

**目标产物**（命名以工具实现为准）：

- `AppLinkTemplates` 或 `GeneratedLinkTemplates`：每实体静态方法，如 `postAppUri(...)`、`postWebPath(...)`、`circleWebPath(...)`。  
- **组合**：`postWebUrl(origin, {postId, visibility})` 由 **生成方法 + `AppPublicContentLinks` 薄层**（仅读 runtime origin）组成；最终实现 **删除** 业务文件中的 `'https://…/post/'` 字面量。

**校验**（建议在 codegen 或 verify 脚本）：

- 每个 `route_id` ∈ `app_routes` 集合。  
- `param_bindings` 的 value 均为该 route `path` 中声明的参数名。

## 5. 云侧（可选）

- 若未来需要 **302 / OG**：在同一 YAML 生成 Go 常量 **path prefix**，与 **网关路由** 注册一致；**本 baseline 不强制** 实现。

## 6. Feature flag / 观测

- **Remote Config** 开关：可控制 `public_web_base_url` 下发与回滚。  
- **观测**：分享/复制成功率、无效链接打开率（若埋点已有，挂 action id）。

## 7. SLO / 回滚

- **SLO**：codegen 与 `app_routes` 不一致时 **构建失败**（或门禁失败）。  
- **回滚**：Remote Config 回退 origin；metadata 路径变更需 **版本化** 与 **重定向** 策略（产品侧）。

## 8. T1–T4 证据矩阵

| 层 | 证据 |
|----|------|
| T1 | `link_templates.yaml` 存在；`route_id` 与 `app_routes` 人工/script 对照表；`verify-metadata` 通过（全仓） |
| T2 | codegen 单测：给定参数 → 期望 scheme / web path 快照 |
| T3 | Widget/集成：复制链接后字符串符合模板；切换 dart-define origin 后前缀变化 |
| T4 | （可选）Universal Link 端到端；云重定向契约测试 |

## 9. 风险

- **user.web.path_template**（`u/{username}`）与 **当前** 公网实际路径不一致时，需运营/SEO 确认后改 metadata **一处**。  
- **chat** 的 web 可分享性涉及 **隐私**；若产品禁止 Web 打开会话，应在业务层 **禁用复制 Web**，而非删 metadata（metadata 仍可用于 **scheme**）。

## 10. 与 `ContentShareTemplateBuilder` 的归并

- `_deeplinkForPermission` 的字符串规则 **迁移为** 读取 **post 实体** 的 `app_deep_link` + `query_rules` 生成结果，**禁止**长期双轨。

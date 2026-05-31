# 端侧目录结构与特性树领域服务映射

> 原则：端侧代码工程必须能从特性树 `L1_domain_service / L2_business_capability / L3_story` 追踪到 app、metadata、service、deploy 和 test。UI、Repository、Router、测试不得维护第二套领域命名。

---

## 一、特性树到端侧工程的关系

| 特性树层级 | 端侧对应 | 测试对应 |
|---|---|---|
| 应用根 | `lib/app`、`lib/core`、`lib/cloud/runtime` | `test/app`、`test/core`、`test/cloud`、`test/patrol` |
| `L1_domain_service` | `lib/ui/{domain}`、`lib/cloud/services/{domain}` | `test/ui/{domain}`、`test/cloud/{domain}` |
| `L2_business_capability` | `lib/ui/{domain}/pages|providers|widgets|models` 下的能力模块 | 能力级 widget/provider/module/integration 测试 |
| `L3_story` | Story 涉及的最小页面、Provider、Repository、DTO 或路由变更 | GWT、contract、widget/provider/API contract 测试 |

Story 不拥有独立架构设计文档；实现约束由所属业务能力 `design.md` 承载。

---

## 二、端侧顶层分层

```text
lib/
├── app/              # 应用壳：路由、主题、Provider 根、shell
├── core/             # 横切能力：design_system、providers、services、tracker
├── cloud/            # metadata 驱动端云交付层：generated runtime + Repository
├── components/       # 跨领域可复用 UI 组件
├── ui/               # 按产品领域服务划分的 UI 模块
├── l10n/             # 国际化
└── features/         # [废弃] 存量迁移区，禁止新建
```

---

## 三、领域服务映射

端侧领域以 `specs/l1_index.yaml` 为准。核心口径：

| `L1_domain_service` | App UI | App cloud | Metadata / Service |
|---|---|---|---|
| `discovery-content` | `lib/ui/discovery`、`lib/ui/content` | `lib/cloud/services/content` | `metadata/content`、`content-service` |
| `circle-community` | `lib/ui/circle` | `lib/cloud/services/circle` | `metadata/social`、`circle-service` |
| `chat-conversation` | `lib/ui/chat` | `lib/cloud/services/chat` | `metadata/messages`、`chat-service` |
| `user-identity-profile-relationship` | `lib/ui/user`、`lib/ui/welcome`、`lib/ui/settings` | `lib/cloud/services/user` | `metadata/user`、`user-service` |
| `assistant-run-learning` | `lib/ui/assistant` | `lib/cloud/services/assistant` | `metadata/assistant`、`assistant-service` |
| `global-search-experience` | `lib/ui/search` | 组合多个领域 Repository | content/chat/user/social 等多个领域 |
| `shared-homepage-network` | `lib/ui/entity`、`lib/ui/content` | `lib/cloud/services/entity` | `entity-service` 及内容/圈子相关领域 |
| `runtime` | `lib/app`、`lib/core`、`lib/cloud/runtime` | runtime generated / http / errors | shared metadata、runtime |

若一个产品领域需要映射多个后端服务，仍以产品领域为特性树 `L1_domain_service`，后端部署映射写入 `specs/l1_index.yaml` 和部署配置。

---

## 四、`lib/cloud` 结构

```text
lib/cloud/
├── runtime/
│   ├── generated/{metadata-domain}/
│   ├── cloud_runtime_config.dart
│   ├── cloud_request_headers.dart
│   ├── http/
│   ├── errors/
│   └── models/
└── services/{domain}/
    ├── {domain}_repository.dart     # Abstract + Mock + Remote
    └── mock/                        # 仅 Repository 内部或测试可使用
```

规则：

- 新增领域先更新 metadata，再 codegen，再新增 Repository。
- UI 只能通过 Provider 访问 Repository。
- Remote 使用 metadata/codegen 路径、operation、surface、route 常量。
- Mock 数据来自 contract seed，不得在 UI 再造第二套列表。

---

## 五、`lib/ui` 结构

```text
lib/ui/{domain}/
├── pages/
├── providers/
├── widgets/
└── models/
```

规则：

- 禁止在 `lib/features/` 下新建页面或领域模块。
- 禁止 UI 直接 import `cloud/services/*/mock/`。
- 禁止 UI 层直接操作跨模块 `Map<String, dynamic>`。
- 页面路由、surface、operation 必须来自 metadata 或 UI 配置真相源。
- 新增或迁移页面必须同步页面横向质量矩阵。

---

## 六、测试目录对齐

```text
test/
├── app/
├── cloud/{domain}/
├── components/
├── core/
├── ui/{domain}/
├── common/
├── alpha/
├── beta/
├── gamma/
└── patrol/
```

测试层映射：

- `T1`：metadata、DTO、错误码、字段策略、脚本校验。
- `T2`：Widget、Provider、模块交互、Story GWT。
- `T3`：API contract、真实服务、真实存储、端云边界。
- `T4`：Patrol、真机旅程、权限、弱网、性能和发布前 UAT。

---

## 七、新增领域服务检查清单

- [ ] `specs/feature-tree/<domain-service>/spec.md` 已定义产品领域边界。
- [ ] `specs/l1_index.yaml` 已登记 app、metadata、service、deploy、test 映射。
- [ ] `contracts/metadata/{domain}/` 已定义业务对象与 API。
- [ ] `make codegen-app` 生成 `cloud/runtime/generated/{domain}/`。
- [ ] `lib/cloud/services/{domain}/` 建立 Repository。
- [ ] `lib/ui/{domain}/` 建立 pages/providers/widgets/models。
- [ ] `test/ui/{domain}` 与 `test/cloud/{domain}` 已有对应测试入口。
- [ ] 新 Story 只有 `spec.md` 与 `acceptance.yaml`，设计约束上收到业务能力层。

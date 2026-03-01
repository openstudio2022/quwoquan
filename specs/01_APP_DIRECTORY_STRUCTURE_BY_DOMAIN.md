# 端侧目录结构规划：按领域服务统一 lib/ui 与 lib/cloud

> **原则**：新建领域服务及页面不再放在 `lib/features/` 下；统一按 metadata 领域划分 `lib/ui/`；模型与端云交付元数据驱动放 `lib/cloud/`。`lib/features/` 为历史遗留，逐步迁移至 `lib/ui/`。

---

## 一、顶层分层

```
lib/
├── app/              # 应用壳（路由、主题、Provider 根）
├── core/             # 横切能力（design_system、providers、services、常量）
├── cloud/            # 端云交付层（metadata 驱动，codegen 产物 + Repository）
├── components/       # 可复用 UI 组件（跨领域）
├── ui/               # 按领域划分的 UI 模块（pages/providers/widgets）
├── l10n/             # 国际化
└── features/         # [废弃] 历史遗留，逐步迁移至 lib/ui/
```

---

## 二、领域与 metadata 映射

| metadata domain | lib/cloud | lib/ui | 说明 |
|-----------------|-----------|--------|------|
| **content** | `cloud/runtime/generated/content/`<br>`cloud/services/content/` | `ui/content/`<br>`ui/discovery/` | 内容详情、创作入口、发现流 |
| **integration** | `cloud/runtime/generated/integration/` | （被 content/entry 等消费） | 位置等外部集成，无独立页面 |
| **chat** | `cloud/services/chat/` | `ui/chat/` | 会话、聊天详情 |
| **user** | `cloud/services/user/` | `ui/user/` | 个人资料、作者页 |
| **circle** | （待建） | `ui/circle/` | 圈子列表、详情、统计 |
| **assistant** | （待建） | `ui/assistant/` | 助理首页、管理、回放 |
| **settings** | — | `ui/settings/` | 应用设置（无独立云领域） |
| **welcome** | — | `ui/welcome/` | 欢迎/引导（无独立云领域） |

---

## 三、lib/cloud 结构（metadata 驱动）

```
lib/cloud/
├── runtime/
│   ├── generated/                    # [codegen] 按 domain 生成
│   │   ├── content/                  # content 域 DTO、metadata
│   │   └── integration/              # integration 域 metadata（如 location）
│   ├── cloud_runtime_config.dart
│   ├── cloud_request_headers.dart
│   ├── http/cloud_http_client.dart
│   ├── errors/
│   └── models/                       # 跨域通用模型（CursorPage 等）
├── content/generated/                # content 域 codegen（errors、behaviors、ui_config）
└── services/
    └── {domain}/                     # 与 metadata domain 对齐
        ├── {domain}_repository.dart  # Abstract + Mock + Remote
        └── mock/
```

**规则**：
- 新增领域 → 先建 `contracts/metadata/{domain}/`，再 `make codegen-app` 生成 `cloud/runtime/generated/{domain}/`
- 模型、DTO、错误码、API 路径等均由 metadata 驱动，禁止硬编码

---

## 四、lib/ui 结构（按领域划分）

```
lib/ui/{domain}/
├── pages/           # 页面入口
├── providers/       # 状态（Riverpod）
├── widgets/         # 页面专属组件
└── models/          # 仅页面可见 ViewModel（非 cloud DTO）
```

### 4.1 领域划分与迁移映射

| 领域 | 目标路径 | 源路径（迁移自） |
|------|----------|------------------|
| **content** | `ui/content/` | 已有：`ui/content/pages/`（article/video/photo_detail） |
| **content.entry** | `ui/content/entry/` | `features/create/`（创作入口） |
| **discovery** | `ui/discovery/` | 已有 |
| **chat** | `ui/chat/` | `features/chat/` |
| **user** | `ui/user/` | 已有：`ui/user/pages/`（author_profile）；迁移：`features/profile/` |
| **circle** | `ui/circle/` | `features/circles/` |
| **assistant** | `ui/assistant/` | `features/assistant/` |
| **settings** | `ui/settings/` | `features/settings/` |
| **welcome** | `ui/welcome/` | `features/welcome/` |

### 4.2 创作入口（create → content/entry）

创作入口属于 **content 域**下的创建流程，使用 integration/location、content/post、social/circle 等。

```
lib/ui/content/
├── entry/                        # 创作入口（原 features/create）
│   ├── pages/
│   │   ├── create_page.dart      # 主创作页
│   │   └── publish_location_selector_page.dart
│   ├── providers/
│   ├── widgets/
│   └── models/
├── pages/
│   ├── article_detail_page.dart
│   ├── photo_detail_page.dart
│   └── video_detail_page.dart
└── ...
```

**迁移**：
- `features/create/pages/` → `ui/content/entry/pages/`
- `features/create/services/`（CreateLocationService 等）→ `cloud/services/integration/` 或保留在 `core/services/`（若为编排层）
- `features/create/models/`（CreateLocationOption 等）→ `cloud/runtime/models/` 或 `ui/content/entry/models/`（若为 ViewModel）

---

## 五、迁移顺序建议

1. **Phase 1：content/entry**  
   - 迁移 `features/create/` → `ui/content/entry/`  
   - 路由、import 批量更新

2. **Phase 2：chat**  
   - 迁移 `features/chat/` → `ui/chat/`

3. **Phase 3：circle**  
   - 迁移 `features/circles/` → `ui/circle/`

4. **Phase 4：user**  
   - 合并 `ui/user/` 与 `features/profile/` → `ui/user/`

5. **Phase 5：assistant、settings、welcome**  
   - 迁移至 `ui/assistant/`、`ui/settings/`、`ui/welcome/`

6. **Phase 6：删除 lib/features/**  
   - 迁移完成后移除 `lib/features/`，更新路由与规则

---

## 六、规则更新要点

- **01-arch-constraints**：明确禁止在 `lib/features/` 下新建；新建一律在 `lib/ui/{domain}/`
- **02-dart-coding**：Feature 层改为 UI 层，约束 `lib/ui/{domain}/`
- **03-testing**：测试路径 `test/ui/{domain}/` 与 `lib/ui/{domain}/` 对齐
- **06-semantic-consistency-audit**：审计路径从 `lib/features/` 改为 `lib/ui/`

---

## 七、test 目录对齐

```
test/
├── cloud/{domain}/           # 契约、DTO、Repository
├── components/               # 组件 widget 测试
└── ui/{domain}/              # 与 lib/ui/{domain}/ 一一对应
    ├── entry/
    │   └── widgets/
    ├── chat/
    ├── circle/
    └── ...
```

---

## 八、检查清单（新建领域服务时）

- [ ] 在 `contracts/metadata/{domain}/` 定义业务对象与 API
- [ ] `make codegen-app` 生成 `cloud/runtime/generated/{domain}/`
- [ ] `lib/cloud/services/{domain}/` 建立 Repository（Abstract + Mock + Remote）
- [ ] `lib/ui/{domain}/` 建立 pages/providers/widgets
- [ ] 禁止在 `lib/features/` 下新建
- [ ] 路由注册到 `app/navigation/`，使用 `ui/{domain}/` 路径

---

## 九、迁移规划任务（tasks）

> 详细任务与 checklist 见 `specs/01_APP_DIRECTORY_MIGRATION_TASKS.md`。验收 traceability（acceptance.yaml）中的 `lib/features/` 路径在对应 Phase 迁移完成后需同步更新为 `lib/ui/{domain}/`。

### Phase 1：content/entry（优先）

- [ ] M1.1 创建 `lib/ui/content/entry/` 目录结构（pages/providers/widgets/models）
- [ ] M1.2 迁移 `features/create/pages/` → `ui/content/entry/pages/`
- [ ] M1.3 迁移 `features/create/services/` → 保留 `core/services/` 或迁至 `cloud/services/integration/`（按编排 vs 纯 HTTP 划分）
- [ ] M1.4 迁移 `features/create/models/` → `ui/content/entry/models/` 或 `cloud/runtime/models/`
- [ ] M1.5 更新 `app/navigation/` 路由与 import
- [ ] M1.6 更新 `create-entry-location-visibility-circle/acceptance.yaml` 的 traceability 路径为 `lib/ui/content/entry/`
- [ ] M1.7 更新 `error-permission-display-semantics`、`page-layout-semantics` 等 acceptance 中的 `local_gate` 路径
- [ ] M1.8 更新 `06-semantic-consistency-audit.mdc` 审计路径
- [ ] M1.9 删除 `lib/features/create/`（或标记为空后移除）

### Phase 2～6：chat、circle、user、assistant/settings/welcome

- [ ] M2.x 按相同模式迁移各领域
- [ ] M6 删除 `lib/features/`，更新所有引用

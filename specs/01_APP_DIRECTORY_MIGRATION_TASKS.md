# 端侧目录迁移任务清单

> 依据 `specs/01_APP_DIRECTORY_STRUCTURE_BY_DOMAIN.md` 执行。迁移完成后，`lib/features/` 内引用需同步更新。

---

## 前置依赖

- [ ] 阅读 `specs/01_APP_DIRECTORY_STRUCTURE_BY_DOMAIN.md`
- [ ] 确认 `01-arch-constraints`、`03-testing` 规则已对齐

---

## Phase 1：content/entry（创作入口）

### 代码迁移

| 任务 | 说明 |
|------|------|
| M1.1 | 创建 `lib/ui/content/entry/pages/`、`providers/`、`widgets/`、`models/` |
| M1.2 | 迁移 `features/create/pages/create_page.dart` → `ui/content/entry/pages/` |
| M1.2 | 迁移 `features/create/pages/publish_location_selector_page.dart` → `ui/content/entry/pages/` |
| M1.3 | 迁移 `features/create/services/` → 保留在 `core/services/`（CreateLocationService、CreateCircleService 为编排层）或新建 `cloud/services/integration/` |
| M1.4 | 迁移 `features/create/models/` → `ui/content/entry/models/`（CreateLocationOption 等为 ViewModel） |
| M1.5 | 批量替换 import：`quwoquan_app/features/create/` → `quwoquan_app/ui/content/entry/` |
| M1.5 | 更新 `app/navigation/` 路由注册 |

### 文档与规则同步

| 任务 | 文件 | 变更 |
|------|------|------|
| M1.6 | `create-entry-location-visibility-circle/acceptance.yaml` | `lib/features/create/` → `lib/ui/content/entry/` |
| M1.7 | `error-permission-display-semantics/acceptance.yaml` | `local_gate` 中 `lib/features/create/` → `lib/ui/content/entry/` |
| M1.7 | `page-layout-semantics/acceptance.yaml` | `local_gate` 中 `lib/features/create/` → `lib/ui/content/entry/` |
| M1.8 | `quwoquan_app/.cursor/rules/06-semantic-consistency-audit.mdc` | 审计路径 `lib/features/` → `lib/ui/` |

### 收尾

| 任务 | 说明 |
|------|------|
| M1.9 | 删除 `lib/features/create/`（迁移并验证通过后） |
| M1.10 | 运行 `make gate` 通过 |

---

## Phase 2：chat

| 任务 | 说明 |
|------|------|
| M2.1 | ✅ 创建 `lib/ui/chat/` |
| M2.2 | ✅ 迁移 `features/chat/` → `ui/chat/` |
| M2.3 | ✅ 更新 import、路由、acceptance、06-semantic-consistency-audit |
| M2.4 | ✅ 删除 `lib/features/chat/` |

---

## Phase 3：circle

| 任务 | 说明 |
|------|------|
| M3.1 | 创建 `lib/ui/circle/`（单数，与 metadata social/circle 对齐） |
| M3.2 | 迁移 `features/circles/` → `ui/circle/` |
| M3.3 | 更新 import、路由、acceptance、06-semantic-consistency-audit |
| M3.4 | 删除 `lib/features/circles/` |

---

## Phase 4：user

| 任务 | 说明 |
|------|------|
| M4.1 | 合并 `features/profile/` 与现有 `ui/user/` → `ui/user/` |
| M4.2 | 更新 import、路由、acceptance、06-semantic-consistency-audit |
| M4.3 | 删除 `lib/features/profile/` |

---

## Phase 5：assistant、settings、welcome

| 任务 | 说明 |
|------|------|
| M5.1 | 迁移 `features/assistant/` → `ui/assistant/` |
| M5.2 | 迁移 `features/settings/` → `ui/settings/` |
| M5.3 | 迁移 `features/welcome/` → `ui/welcome/` |
| M5.4 | 更新 import、路由、acceptance、06-semantic-consistency-audit |
| M5.5 | 删除对应 `lib/features/` 子目录 |

---

## Phase 6：删除 features

| 任务 | 说明 |
|------|------|
| M6.1 | 确认 `lib/features/` 已无业务代码 |
| M6.2 | 删除 `lib/features/` |
| M6.3 | 移除规则、文档中对 `lib/features/` 的残留引用 |
| M6.4 | `make gate` 通过 |

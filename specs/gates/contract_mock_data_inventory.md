# Contract-Driven Mock Data Inventory

> 目的：记录端侧仍散落的 mock/test 数据，并作为迁移到 `contracts/metadata/**/test_fixtures` 的治理清单。

## 范围

本清单覆盖端侧 `Mock*Repository`、`lib/cloud/services/**/mock`、`lib/core/mock/prototype_mock_data.dart` 与首批高价值测试。规则是：新增或改造 alpha/beta 用例时，只引用 scenario id / seed ref，不再在测试或 UI 中复制业务数据。

## 迁移分级

| 优先级 | 域 | 当前主要来源 | 目标 fixture | 首批迁移范围 | 状态 |
|---|---|---|---|---|---|
| P0 | assistant | `assistant_scenarios.json` + `MockAssistantRepository` 内置数据 | `contracts/metadata/assistant/test_fixtures/scenarios/assistant_scenarios.json` | 找私助流式问答、技能订阅 seed | 已启动 |
| P1 | content/discovery | `ContentMockData`、`PrototypeMockData.discovery*` | `contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json` | 发现流 photo/video/article/moment、详情 hydration、搜索 | 迁移中 |
| P1 | circle | `CircleMockData` | `contracts/metadata/social/circle/test_fixtures/scenarios/circle_scenarios.json` | 圈子列表、详情、默认群、成员、文件 | 迁移中 |
| P1 | chat | `ChatMockData` | `contracts/metadata/messages/chat/test_fixtures/scenarios/chat_scenarios.json` | inbox、会话详情、成员、消息、联系人 | 迁移中 |
| P2 | user/entity | `UserProfileMockData`、`HomepageMockData` | `contracts/metadata/user/**/test_fixtures`、`contracts/metadata/entity/**/test_fixtures` | 主页、关系态、作品/生活记录 | 待迁移 |
| P2 | notification | `notification/test_fixtures/scenarios/notification_scenarios.json` | generated `AlphaFixtureBundle` + typed `AlphaAppMessage*` Facet | AppMessage 列表、未读数、读取状态 | 已完成（2026-07-14，旧 Repository/DTO 已删除） |
| P3 | rtc/realtime/integration/ops | 各 `Mock*Repository` 内存数据 | 对应域 `test_fixtures` | 协议最小样例、状态切换 | 待迁移 |

## 禁止新增

- 禁止在 `lib/ui/**`、`lib/app/**`、`lib/core/**` 新增业务 mock 数据。
- 禁止在新增测试中直接引用 `ContentMockData` / `ChatMockData` / `CircleMockData` / `PrototypeMockData` 作为业务 fixture。
- 禁止为 alpha/beta/gamma 复制三套测试问题、标题、消息正文或圈子名称。

## 未迁移对象冻结规则

- 清单中的未迁移 `Mock*` 仅作为待删除存量冻结；不得新增接口、调用点、业务数据或兼容 alias。
- 对象一旦进入迁移 packet，必须在同一 packet 内切换到 generated contract + typed Facet，并删除旧 Repository/DTO/decoder；不得保留双主线或失败回退 Mock。
- `PrototypeMockData` 只允许随尚未迁移对象冻结，不得被新测试、UI 或 Remote composition 引用；`AppContent` 已删除，剩余切片必须随各自对象 packet 迁入 `quwoquan_cloud_mock` 后删除。

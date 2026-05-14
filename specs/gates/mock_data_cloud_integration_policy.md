# Mock 数据 · 端云一体化 · 正式发布隔离 — 总策略

> **目标**  
> 1. **一键切换**：开发/内测通过 **单一配置**（如 `AppDataSourceMode` + dart-define / flavor）在 **端侧 Mock** 与 **云侧 Remote** 间切换。  
> 2. **完全隔离**：**域名 Mock 数据与假用户路径** 只存在于 **`Mock*Repository` / `cloud/services/*/mock/` / `test/`**，**不得**出现在 `lib/ui`、`lib/app`、`lib/core` 的业务链路中。  
> 3. **正式发行**：**Release/商店包** 不携带 **可切换 Mock 的配置入口**、**测试专用 dart-define 默认值**、以及 **未剥离的 Mock 实现**（见下文「发行形态」）。  
> 4. **编译单元隔离**：**禁止**在 `lib/**` 与业务代码 **同一源文件** 内定义「仅测试/夹具用」类型、配置或导出（见 **§4.1**）。运行时 `kDebugMode` 分支仍会把两侧代码编进同一产物；**真正零耦合**依赖 **文件级/包级边界**，而非仅靠访问控制。

---

## 1. 当前架构与缺口（摘要）

| 层级 | 合规形态 | 典型缺口 |
|------|-----------|----------|
| **Provider** | 仅 `ref.watch(xxxRepositoryProvider)` | `appDataSourceModeProvider` 已存在，但部分 UI 仍绕过 |
| **Mock*Repository** | 仅在此读 `*MockData` | `cloud/services/*/*_repository.dart` 内混用可接受；**UI 直接 import `.../mock/`** 不可接受 |
| **Remote*Repository** | HTTP + codegen DTO | `RemoteAppContentRepository` 全量委托 Mock 等 **伪 Remote** |
| **UI 模型** | 无 `prototype*` 域名实体 | `ChatContactsRow.prototype*` 等 **const 假数据** |
| **单文件边界** | 业务 `.dart` 仅含发布所需 API | 与业务类 **同文件** 的 fake、`@visibleForTesting` 扩权 API、仅测用 `typedef`/常量 — **仍进入 Release 编译单元** |

---

## 2. 目标数据流（合并「测试数据」与端云）

```
┌─────────────────────────────────────────────────────────────┐
│  UI / AppShell / Core widgets                                │
│  只依赖：Repository 抽象接口 + Riverpod Provider               │
└───────────────────────────┬─────────────────────────────────┘
                            │
            ┌───────────────▼───────────────┐
            │  appDataSourceModeProvider     │
            │  + dart-define / flavor (prod) │
            └───────────────┬───────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         ▼                                      ▼
  MockChatRepository                    RemoteChatRepository
  （仅引用 chat/mock/*）                 （仅 HTTP + DTO）
```

- **「测试数据」** 在工程上等同于 **MockRepository 的内存数据源**，与 **`test/` fakes** 同源策略；**禁止**在 UI 再复制一份。  
- **切换配置**：  
  - **运行时**：开发者设置写 `AppDataSourceMode`（仅 **非正式包** 展示入口，见 §5）。  
  - **编译期**：`--dart-define=APP_DATA_SOURCE=remote|mock`（或 flavor）决定 **默认模式** 与 **是否链接 Mock 实现**。

---

## 3. 分阶段规划（与记录清理对齐）

| 阶段 | 内容 | 退出标准 |
|------|------|----------|
| **P0 看护** | `verify_ui_mock_isolation.py` + allowlist **只缩不扩** | 新增/改动 `lib/ui|app|core` **不得**新增 mock import / 内嵌 prototype 行 |
| **P0b 同文件测试剥离** | 审计 `lib/**`：测试夹具/fake/仅测 API 迁出至 `test/**`（或 dev 专用包）；见 **§4.1** | `lib` 内 **无**「仅 test 引用」的顶层声明与业务混文件；可选门禁 `verify_lib_no_test_only_symbols.py`（后续） |
| **P1 去 UI 直连** | 圈子/联系人/收件箱等改走 `*Repository` | allowlist 中 `import_cloud_mock` 类条目清零 |
| **P2 伪 Remote** | `RemoteAppContentRepository` 等改为真 Remote 或空态 | 无「Remote 委托 Mock」用于生产路径 |
| **P3 身份与全局** | `currentUserIdProvider` 等与 Auth 对齐 | 不依赖 `ChatMockData.currentUserProfileId` |
| **P4 发行剥离** | prod flavor / 条件编译 | Release 包体与入口满足 §5 |

**Mock/远端与生产包完全分离（契约包、Mock→`test/`、双 pubspec 等）**：**暂缓**，触发条件与清单见 **[`mock_production_separation_backlog.md`](mock_production_separation_backlog.md)**（与 P4 互补；非当前必做项）。

---

## 4. 目录与依赖红线（强制）

| 允许 | 禁止（正式代码路径） |
|------|----------------------|
| `lib/cloud/services/{domain}/mock/*.dart` | `lib/ui/**` import `.../mock/` |
| `Mock*Repository` 内使用 `*MockData` | `lib/core/**`（除 allowlist 过渡期）import `.../mock/` |
| `test/**` 使用 fakes | `lib/ui/**/models/**` 内 **域名** `static const` 列表（头像 URL、业务 id） |
| `core/mock/prototype_mock_data.dart` **仅**被 Mock 层与过渡期 allowlist 引用 | 正式发布 **依赖** `prototype_mock_data` 的 Remote 路径 |

---

## 5. 正式发行：不要带「测试代码 / Mock 配置」

**推荐组合（需在后续清理任务中落地）：**

1. **Flavor / 多入口**  
   - `lib/main_dev.dart`：可注册 Mock、展示开发者开关。  
   - `lib/main_prod.dart`：**仅**注册 Remote Provider；**不** import `mock/` 下实现文件（利于 tree-shake）。

2. **dart-define**  
   - `APP_DATA_SOURCE=remote`：**默认强制 Remote**；CI 产正式包必传。  
   - 正式包 **不** 定义 `ALLOW_MOCK=1` 之类开关。

3. **UI 入口**  
   - `DeveloperSettingsPage` 中数据源切换：**`kDebugMode` 或 flavor 门控**，Release **不编译/不展示**。

4. **静态门禁**  
   - Release 构建流水线：`flutter build ... --dart-define=APP_DATA_SOURCE=remote` + （可选）**第二构建**验证 Mock 未链接（依赖 P4 拆分）。

### 5.1 功能规格：发布态 vs 开发测试态（验收口径）

以下条款作为 **产品/工程共用** 的「功能规格」，与门禁脚本、`AppDataSourceMode` 实现及 CI 对齐；**不**替代各域业务 PRD。

#### A. 最终发布态（商店包 / `Release` 构建）

| ID | 要求 | 验证方式 |
|----|------|----------|
| **R1** | **默认数据源为云侧**：进程启动后有效模式为 **Remote**（未显式覆盖时）；与 `APP_DATA_SOURCE`、Release 默认策略一致。 | 集成/手测 + 代码审阅 `AppDataSourceModeNotifier` |
| **R2** | **无「切 Mock」用户入口**：任意面向用户的界面（含「开发者」类设置）**不得**在 Release 下提供 Mock/Remote 切换或等价开关。 | 代码审阅 `kReleaseMode` / flavor；UI 测试可选 |
| **R3** | **无测试目录进包**：`test/` **不**作为应用入口依赖；发布产物不单独打包测试源码（Flutter 默认即如此）。 | 构建产物检查 |
| **R4** | **业务壳层不直连 mock 目录**：`lib/ui`、`lib/app`、`lib/core` **不得** `import .../cloud/services/*/mock/`；不得内嵌门禁规则所禁的域名 `prototype*` 行。 | `python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py` |
| **R5** | **正式构建显式 remote**：CI 上生成上架/交付用二进制时 **必须** 传入 `--dart-define=APP_DATA_SOURCE=remote`（或与策略等价的 flavor/入口约定）。 | CI 配置审阅 |
| **R6** | **伪 Remote 不得充当线上路径**：`Remote*Repository` 不得将生产路径 **整表委托** Mock 内存数据（P2 退出标准）。 | 代码审阅 + 契约测试 |

**说明（二进制与 Mock 类）**：在 **未做 P4 条件编译/拆入口** 前，Dart AOT **仍可能**链接与 `Remote` 同库的 `Mock*Repository` 实现；**R1～R6 保证的是运行时与工程边界**，**不**自动保证「可执行文件内零 Mock 字节」。「物理零 Mock」为 **P4 增强目标**，见 §5 上文与 P4。

#### B. 开发 / 内测态（Debug、Profile、或显式 mock 定义）

| ID | 要求 | 验证方式 |
|----|------|----------|
| **D1** | **一键切换**：通过 **单一全局状态**（`appDataSourceModeProvider` / `AppDataSourceMode`）在 **Mock** 与 **Remote** 间切换；全应用 Repository 消费者无第二套并行开关。 | 手测开发者页 + Provider 审阅 |
| **D2** | **切换入口仅非 Release**：数据源开关仅在 **非 `kReleaseMode`** 下展示（或 dev flavor）；与 §5 上文「开发者窗口」约定一致。 | 代码审阅 |
| **D3** | **可选编译期默认**：`--dart-define=APP_DATA_SOURCE=mock` 可用于本地/CI 默认 Mock，**不得**作为商店流水线默认值。 | CI 与本地脚本分离 |
| **D4** | **Mock 数据唯一真相**：域名假数据仅在 `Mock*Repository`、`cloud/services/*/mock/`、`test/**`（及 `core/mock/prototype_mock_data.dart` 过渡期规则）；UI 只经 Repository。 | `verify_ui_mock_isolation` + PR 自检 |
| **D5** | **端云契约驱动测试数据**：新增 alpha/beta/gamma 用例先写 `contracts/metadata/**/test_fixtures/scenarios/*.json`，alpha MockRepository 从 seed 初始化，beta/gamma 云侧 reset+seed 后走 Remote。 | `verify_contract_mock_data_inventory.py` + 目标 integration |

#### C. 「测试代码」与「业务代码」用语边界（避免误伤）

| 类别 | 是否视为「不得进发布的测试代码」 | 说明 |
|------|-----------------------------------|------|
| `test/` | **是**（不进业务包） | 端侧测试统一位于 `test/common|alpha|beta|gamma|patrol` |
| `TestKeys`、语义化 `Key` | **否**（允许） | 自动化 / 可及性用，**非**单元测试源码 |
| `debugPrint`、断言 | **否**（允许，但应克制） | 不替代正式日志管线；大量调试输出应门控 |
| `Mock*Repository`、`*MockData` | **实现上在 lib 内** | **运行时** Release 默认不走；**字节级剔除** 依赖 P4 |

---

## 6. 命令与本地自检

**与 CI `gate_repo.sh --scope app` 对齐的 Python 门禁（建议本地改 UI 前必跑）：**

```bash
# 横向看护（UI/App/Core 不得直连 cloud …/mock/）
python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py

# lib 内测试专用符号（createForTest 等，见 lib_test_only_symbols_allowlist.yaml）
python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py

# UI 层 AppDataSourceMode.mock / appDataSourceModeProvider 引用棘轮（只降不升，见 ui_app_data_source_mode_baseline.json）
python3 quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py

# 与仓库 app gate 一致（含 flutter analyze、上述脚本、flutter test 等）
bash agent_ops/gate/gate_repo.sh --scope app
```

**Makefile 等价目标（节选）：** `make verify-app-mock-isolation`、`make verify-app-lib-test-only-symbols`、`make verify-app-ui-app-data-source-mode-ratchet`。

**正式构建（与 §5.1 R5、`main_prod` 入口一致）：** CI 生成上架/交付用二进制时 **必须** 传入 `--dart-define=APP_DATA_SOURCE=remote`，与 [`quwoquan_app/lib/main_prod.dart`](../../quwoquan_app/lib/main_prod.dart) 中锁 Remote 的 Provider override 一致。

```bash
flutter build ipa --dart-define=APP_DATA_SOURCE=remote
# 或 apk/appbundle 等价
```

（具体 target 以项目交付脚本为准。）

---

## 7. 相关产物索引

| 产物 | 说明 |
|------|------|
| [`ui_mock_isolation_allowlist.yaml`](./ui_mock_isolation_allowlist.yaml) | 过渡期豁免；**清理后须删行** |
| [`quwoquan_app/scripts/env/verify_ui_mock_isolation.py`](../../quwoquan_app/scripts/env/verify_ui_mock_isolation.py) | 门禁实现 |
| [`quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py`](../../quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py) | UI 数据源分支棘轮（[`ui_app_data_source_mode_baseline.json`](./ui_app_data_source_mode_baseline.json)） |
| [`quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py`](../../quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py) | lib 内测试专用符号 |
| [`.cursor/rules/08-mock-data-isolation.mdc`](../../.cursor/rules/08-mock-data-isolation.mdc) | Agent / 人工规则 |
| [`page_horizontal_quality_pr_checklist.md`](./page_horizontal_quality_pr_checklist.md) | PR 勾选 **Mock 隔离** |
| [`CR-20260329-007-mock-data-isolation-gate.yaml`](../changelog/CR-20260329-007-mock-data-isolation-gate.yaml) | 变更登记 |

---

## 9. 目标目录结构（Mock 接口 · 配置 · 测试隔离）

> **目的**：把「接口 / 配置」与「假数据实现 / 测试夹具」在 **路径上** 分开，便于从 `lib/ui`、`lib/core` **迁入迁出** 时有一致落点；**测试** 仍按与发布代码相同的 **域（cloud / ui / core / assistant）** 分层，但 **共享夹具** 必须落在 **单独根目录**，避免与用例文件混放、避免误 import 进 `lib`。

### 9.1 `lib/`（发布代码）— 按域并列 Mock / Remote，配置无假表

以 `chat` 域为例（其它域 **同形**）：

```text
quwoquan_app/lib/cloud/services/chat/
  chat_repository.dart              # 抽象接口 + 双方共用的 DTO/扩展（无 HTTP、无大段内存假表）
  mock/
    chat_repository_mock.dart       # MockChatRepository（由 chat_repository.dart 拆出，可渐进）
    chat_mock_data.dart             # 仅本域内存场景数据（现有文件可保留名，逐步瘦身）
  remote/
    chat_repository_remote.dart     # RemoteChatRepository（HTTP + codegen DTO）
```

- **接口**：以 **`{domain}_repository.dart` 内 `abstract class XxxRepository`** 为唯一对外契约；`app_providers` 仅依赖 **抽象** + `mock/`、`remote/` 下的 **具体类**。  
- **配置**（数据源模式、dart-define、是否允许 Mock）：集中在独立目录，**不**与某一域 `mock_data` 同文件：

```text
quwoquan_app/lib/core/data_source/   # 建议新建；从 app_providers 渐进抽出
  app_data_source_mode.dart          # AppDataSourceMode、SharedPreferences key、notifier
  data_source_policy.dart            # 可选：kDebugMode / flavor 下是否展示开发者切换
```

- **God 对象迁移方向**：[`lib/core/mock/prototype_mock_data.dart`](../../quwoquan_app/lib/core/mock/prototype_mock_data.dart) 按域 **下沉** 到各 `mock/{domain}_mock_data.dart`；[`app_content_repository.dart`](../../quwoquan_app/lib/core/services/app_content_repository.dart) 按能力 **拆回** 各域 Repository 或 **薄门面**（仅组合接口、不持有假表）。

### 9.2 `test/` — 与 `lib` 域划分一致 + **`support/` 单独隔离根**

保持现有习惯（与发布侧对齐）：

```text
quwoquan_app/test/
  cloud/{domain}/contract/          # 契约 / Mock+Remote 对齐（如 chat_repository_contract_test）
  cloud/{domain}/...                # 其它云侧单测
  ui/{domain}/...                   # 页面 / Widget / journey（与 lib/ui 域一致）
  core/...                          # 与 lib/core 对齐
  assistant/...                     # 与 lib/assistant 对齐
  components/...                    # 与 lib/components 对齐
```

**单独目录隔离（强制语义）** — 仅放 **测试共享** 物，**不**镜像某一单页、**不**被 `lib` import：

```text
quwoquan_app/test/support/
  fakes/                            # 跨用例 FakeHttpClient、FakeRepository、Riverpod override 桩
    {domain}/                       # 可选：与 cloud 域对齐，便于查找
  fixtures/                         # JSON / 二进制 / 大段样例（按域分子目录可选）
  harness/                          # pumpApp、测试用 ProviderScope、路由桩等
```

- **规则**：`test/support/**` 内 **不得** `import flutter_test` 以外的 app 代码仅通过 **公开 API**；若需测 `lib` 私有实现，应通过 **同测目录** 下的 `*_test.dart` 或 **export 测试专用 API**（避免回到 §4.1 禁止的同文件混写）。  
- **contract 测试**：继续放在 `test/cloud/{domain}/contract/`，数据源用 **`Mock*Repository` 或 `test/support/fakes`**，**不**从 `lib/.../mock/` 再拷一份 Map。

### 9.3 与环境测试目录的关系

- E2E / Patrol 等统一放在 **`quwoquan_app/test/`** 下：环境无关放 `test/common`，本地端侧 mock 放 `test/alpha`，本地端云集成放 `test/beta`，云侧集成放 `test/gamma`，真机系统能力放 `test/patrol`。
- 是否跑设备/模拟器由 runner 的 `-d <device>` 参数决定，不再通过目录名表达。

### 9.4 移植清单（混入代码落点速查）

| 当前混入形态 | 目标落点 |
|--------------|----------|
| UI/Provider 内 `const` 假列表 | 对应域 `mock/{domain}_mock_data.dart` + `Mock*Repository` 方法 |
| UI `import .../mock/` | 删除 import；改 `ref.read(xxxRepositoryProvider)` |
| `core` 内 Prototype 大表 | 拆入各域 `mock/*_mock_data.dart` |
| Widget 测共用 pump / fake | `test/support/harness/`、`test/support/fakes/` |
| 契约测试 JSON | `test/support/fixtures/{domain}/` |

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-29 | 初版：策略 + 分阶段 + 发行约束 + 与门禁对齐 |
| 2026-03-29 | 增补 §4.1：禁止 lib 内业务与测试/夹具同文件混写；阶段 P0b；后续 verify_lib_no_test_only_symbols 建议 |
| 2026-03-29 | 新增 §9：Mock/Remote/配置目录目标；`test/support` 隔离根与移植速查表 |
| 2026-03-30 | **§5.1 功能规格**：冻结「发布态 R1–R6 / 开发测试态 D1–D4 / 测试代码用语边界」验收表；明确 R1–R6 为运行时与工程边界、物理零 Mock 属 P4 |
| 2026-04-12 | §6 增补：`verify_ui_app_data_source_mode_ratchet`、`verify_lib_no_test_only_symbols`、Makefile 目标与正式构建 define；索引表增加棘轮脚本 |
| 2026-04-12 | **P1 进展**：`mockDataSourceActiveProvider` / `remoteDataSourceActiveProvider` 收敛于 [`app_content_repository.dart`](../../quwoquan_app/lib/core/services/app_content_repository.dart)；`lib/ui/**`（豁免开发者设置页）对 `AppDataSourceMode.mock` / `appDataSourceModeProvider` 的散落引用棘轮基线已 **清零**（见 [`ui_app_data_source_mode_baseline.json`](./ui_app_data_source_mode_baseline.json)）；[`app_content_repository_provider`](../../quwoquan_app/lib/cloud/services/app_content/app_content_repository_provider.dart) 改为依 `remoteDataSourceActiveProvider` 选型 |

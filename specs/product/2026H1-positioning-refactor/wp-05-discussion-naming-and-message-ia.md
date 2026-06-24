# WP5 · 「讨论」命名统一与消息页 IA（端云）

> ⚠️ **命名回滚（2026H2 · 「发起群聊商用重构」会话）**：本包对 **chat-conversation 群会话** 的「群聊→讨论」改名已被回滚。消息域群会话前台词回到 **「群聊」**，详见 `00_GLOBAL_TERMINOLOGY.md` §18.6。
> 本文档下列涉及 chat 群会话的「讨论」改名条目（消息/联系二级胶囊、发起入口、群管理文案、Web 消息 Tab、`startGroupChat`/`exitGroupChat` 等）**以 §18.6 为准（保留「群聊」）**。
> 仍然有效的「讨论」口径：实体主页「讨论」Tab、圈子内容「讨论」Tab、全局检索跨对象聚合「讨论」分区、交集「共同讨论」。`group` 作为 wire/filter/type 机器值不变。

> 树归属：`chat-conversation/commercial-message-system`（修订）+ `global-search-experience`（搜索分组改名）
> 影响 Journey：`message-social-connection`、`message-group-entry-matrix`、`global-search-query-and-filter`
> 验收意图：GWT + SIT；测试证据：T1 / T2

## 1. 背景与现状

- 最新复核结论：WP5 仍未完整落地，当前实现只在对象页/圈子页局部使用「讨论」，chat、Web、搜索链路、门禁与测试仍保留大量旧口径。
- 同一 group 概念目前仍有 4 个用户侧名字：
  - `群聊`：chat 域主名（`ui_text_constants.dart` 约 30 处 + Web 壳 `webPcMessagesTabGroups`）；
  - `趣群`：`contactsTabFunGroup`（未推广）；
  - `群组`：搜索域（`search_models.dart`、codegen `search_registry.g.dart`、`search_network_results_page.dart`）；
  - `讨论`：圈子壳 groups Tab 与实体壳 reviews Tab（已是目标命名）。
- 消息页 IA（`lib/ui/chat/pages/chat_page.dart`）：已冻结「消息/联系」双 Tab；消息二级胶囊 `全部/未读/群聊/私聊/通知`，联系二级 `全部/互相关注/圈子/群聊`；两行布局已达标；小趣为全局顶栏入口。
- 术语决策已冻结于 `00_GLOBAL_TERMINOLOGY.md` §18：用户侧统一 `讨论`；`私聊` 保留；`趣群` 废弃；禁用词 `空间/频道/论坛/群组`（群概念语境）。

## 2. 功能规格

### 2.0 统一概念基线（本包必须遵守）

- 本包虽然主焦点是「讨论」命名，但其消息系统与联系人体系必须兼容新的长期动作总线：用户的长期动作只有 `关注人 / 关注实体 / 加入圈子`，内容无长期动作，不再引入“收藏夹式”对象沉淀语义。
- 消息、联系、打招呼、互相关注都属于“连接”与“交流”家族；不得为“收藏内容后再聊”这类旧心智新增前台概念。
- 本包术语门禁（`verify-app-concept-naming`）扫描范围同步纳入内容动作禁用词：`收藏 / 关注内容 / 稍后看`（用户可见文案层）。**注**：上述禁用词在 `lib/**` 现状已清零（基线修正已落地），本项为**防回归**门禁项，不是清理待办。
- 交集口径以 `specs/product/intersection-definition-and-application.md` 为准：六个母表达为 `共同关注的人 / 共同圈子 / 共同兴趣 / 共同地点 / 共同校友 / 共同讨论`；`favorite`/收藏全链路退场，足迹为私有只读且不产生交集、影响数字或消息提醒。

### 2.1 命名统一（用户可见层）

- 消息页二级胶囊：`全部 / 未读 / 讨论 / 私聊 / 通知`（「群聊」→「讨论」；保留「未读」）。
- 联系页二级胶囊：`全部 / 互相关注 / 圈子 / 讨论`（「群聊/趣群」→「讨论」）。
- 搜索域：搜索范围、结果分组、加载文案「群组」→「讨论」（经 metadata 改 search registry → `make codegen-app`，禁手改 `search_registry.g.dart`）。
- Web 宽屏壳：`消息/联系人/群聊` 中「群聊」→「讨论」。
- chat 域文案常量清理：`startGroupChat`（发起讨论）、`exitGroupChat`（退出讨论）等约 30 处按语境改写；**群管理深层角色词（群主/群管）过渡保留**（§18.2）。
- `contactsTabFunGroup`（趣群）删除或改值为「讨论」。
- 实体侧群名模板 `'$title 讨论群'` 统一为 `'$title 讨论'`（`entity_repository.dart`）。
- 通用消息能力词保留：`聊天记录 / 聊天消息 / 聊天会话` 不属于本次禁用词，禁止误杀。

### 2.2 消息页 IA 微调（不推翻双 Tab）

- 保留「消息/联系」双一级 Tab 与两行布局、A-Z 索引、星标分组、打招呼收件箱置顶行。
- 云侧 filter 枚举语义不变（`group` 继续作为机器值），仅用户可见 label 改「讨论」；如需新增 label key，经 `messages/conversation` metadata 文案层（避免机器枚举与显示语言耦合）。
- 小趣维持全局顶栏入口；消息「通知」子 Tab 继续承载小趣提醒 AppMessage 行。

### 2.3 术语门禁（新增）

- 新增 `quwoquan_app/scripts/runtime/verify_concept_naming.py`：扫描 `lib/**` 用户可见文案常量中的禁用词（`空间/频道/论坛/群组/趣群/群聊` 作为群概念语境；「频道」放行首页内容频道语境，用 allowlist 区分），基线只减不增。
- 串入 `agent_ops/gate/gate_repo.sh` 的 `run_app` 与 `Makefile`（`verify-app-concept-naming`）。
- 门禁首发强拦截范围为 App 用户可见文案 + search metadata 展示 label；service/codegen/seed 中 `favorite` 真实残留登记为 WP1 阻塞项，不由 WP5 直接修复。

### 2.4 spec 修订

- 修订 `specs/feature-tree/chat-conversation/commercial-message-system/spec.md` §3：二级胶囊 label 更新为「讨论」，登记术语依据（§18）。

## 3. 周边契约

- 不改 message-home / contact-home / group-home API 形状与 filter 机器枚举值（`group/direct/...` 保持）。
- `ui_text_constants.dart` / `app_concept_constants.dart` 批量改名为本包独占；其他包期间只追加新 key。
- 搜索 registry 改名经 metadata → codegen；同步核对搜索契约测试。

## 4. 改动范围

- `quwoquan_app/lib/core/constants/ui_text_constants.dart`、`app_concept_constants.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_page.dart`（二级胶囊 label）及 chat 域涉及文案的页面
- `quwoquan_app/lib/core/models/search_models.dart`、搜索 metadata + `search_registry.g.dart`（codegen）、`lib/ui/search/pages/search_network_results_page.dart`
- `quwoquan_app/lib/app/shell/web_main_app_shell.dart`
- `quwoquan_app/lib/cloud/services/`（entity 群名模板）
- 新增 `quwoquan_app/scripts/runtime/verify_concept_naming.py` + Makefile + gate 挂接
- `specs/feature-tree/chat-conversation/commercial-message-system/spec.md`
- 相关 widget 测试与 fixture 文案同步

## 5. 准出要求

1. 全仓 `lib/**` 用户可见文案中 group 概念仅出现「讨论」；`verify_concept_naming.py` 全绿且基线清零（群概念语境）。
2. T2：chat 双 Tab + 二级胶囊 widget 测试更新后全绿（两行布局、索引、星标回归）。
3. T2：搜索结果分组显示「讨论」；搜索契约测试绿。
4. codegen 产物经 metadata 再生成（hash 比对绿），无手改。
5. `bash agent_ops/gate/gate_repo.sh --scope app` 全绿；spec 修订完成。
6. `聊天记录 / 聊天消息 / 聊天会话` 作为消息能力词仍可正常出现；`群主 / 群管` 仅可在深层管理权限语境过渡保留。
7. WP1 防回归扫描在 App 用户可见层生效：不得新增 `收藏 / 稍后看 / 关注内容 / 共同关注内容`；旧 kind 不回流。

## 6. 验收标准（GWT 样例）

- Given 打开消息页，Then 二级胶囊为 全部/未读/讨论/私聊/通知；联系页为 全部/互相关注/圈子/讨论。
- Given 搜索「摄影」，Then 结果分组标题为「讨论」而非「群组」。
- Given 全局搜索 `lib/` 用户可见常量，Then 无「趣群」「群组（前台）」「空间/频道/论坛（群概念）」残留。
- Given 从圈子页「讨论」Tab 进入某讨论，Then 会话页及设置页文案不再出现「群聊」一级概念词（深层管理角色词除外）。

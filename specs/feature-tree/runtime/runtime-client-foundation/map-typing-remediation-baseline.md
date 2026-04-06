# Map / 弱类型数据整改 — 基线快照

_Generated: 2026-04-04 14:46 UTC_ (`scripts/report_map_typing_baseline.py`)

## 1. 口径

- **扫描根**: `quwoquan_app/lib/**/*.dart`
- **排除**: `*.g.dart`（codegen 内 `toMap` 等不计入待清零口径）
- **匹配**: 字面量 `Map<String, dynamic>`（含中间有空格变体）

## 2. 汇总

| 指标 | 值 |
|------|-----|
| `Map<String, dynamic>` 出现次数 | **2199** |
| 涉及文件数 | **280** |
| `contracts/metadata/**/service.yaml` 文件数（约） | **23** |

## 3. 按顶层目录（lib 下第一级）

| 目录 | 次数 |
|------|------|
| `assistant/` | 1091 |
| `cloud/` | 716 |
| `ui/` | 178 |
| `core/` | 173 |
| `components/` | 34 |
| `analytics/` | 5 |
| `app/` | 2 |

## 4. 热点文件 Top 40（按次数）

| 次数 | 路径 |
|------|------|
| assistant/orchestration/local_phase_execution_owner.dart | `195` |
| cloud/services/circle/circle_repository.dart | `121` |
| cloud/services/content/content_repository.dart | `91` |
| cloud/services/user/user_profile_repository.dart | `85` |
| assistant/infrastructure/llm/llm_provider.dart | `75` |
| assistant/tool/impl/web/websearch_tool.dart | `71` |
| core/services/app_content_repository.dart | `49` |
| assistant/reasoning/runtime/react_runtime.dart | `43` |
| assistant/tool/impl/search/search_tool.dart | `42` |
| cloud/services/assistant/assistant_repository.dart | `30` |
| cloud/services/chat/mock/chat_repository_mock.dart | `29` |
| ui/assistant/providers/assistant_conversation_controller.dart | `28` |
| assistant/protocol/persisted_assistant_turn.dart | `27` |
| cloud/services/rtc/rtc_repository.dart | `27` |
| core/mock/prototype_mock_data.dart | `25` |
| ui/circle/widgets/section_creations.dart | `24` |
| cloud/services/app_content/app_content_repository_mock.dart | `22` |
| cloud/services/entity/entity_repository.dart | `21` |
| assistant/conversation/orchestration/session_manager.dart | `20` |
| assistant/orchestration/phases/bootstrap_phase.dart | `20` |
| cloud/runtime/generated/entity/homepage_models.dart | `20` |
| cloud/services/chat/remote/chat_repository_remote.dart | `19` |
| cloud/services/user/auth_repository.dart | `18` |
| cloud/services/chat/mock/chat_mock_data.dart | `17` |
| cloud/services/user/invite_repository.dart | `17` |
| core/services/search_repository.dart | `17` |
| cloud/services/content/mock/content_mock_data.dart | `16` |
| assistant/orchestration/phases/understand_phase.dart | `15` |
| assistant/skill/execution/assistant_skill_executor.dart | `15` |
| assistant/tool/runtime/tool_metadata_registry.dart | `15` |
| ui/content/article_document_models.dart | `15` |
| assistant/application/assistant_journey_projector.dart | `14` |
| assistant/orchestration/conversation_spine.dart | `14` |
| cloud/services/entity/mock/homepage_mock_data.dart | `14` |
| core/services/cache/local_chat_search_sync_service.dart | `14` |
| assistant/context/assembly/evidence_evaluator.dart | `13` |
| assistant/skill/domain/skill_manifest.dart | `13` |
| assistant/transcript/replay/assistant_replay_record.dart | `13` |
| assistant/transcript/row/assistant_transcript_timeline_row.dart | `13` |
| cloud/services/ops/ops_event_repository.dart | `13` |

## 5. Repository `Future<...Map<String,dynamic>>` 粗检

以下为抽象/实现文件中 `Future<...Map<String, dynamic>>` 形态的大致计数（非语义分析）。

| 文件 | 粗计数 |
|------|--------|
| `quwoquan_app/lib/cloud/services/content/content_repository.dart` | ~57 `Future<...Map<String,dynamic>>` shapes |
| `quwoquan_app/lib/cloud/services/circle/circle_repository.dart` | ~57 `Future<...Map<String,dynamic>>` shapes |
| `quwoquan_app/lib/cloud/services/chat/chat_repository_api.dart` | ~9 `Future<...Map<String,dynamic>>` shapes |
| `quwoquan_app/lib/cloud/services/user/user_profile_repository.dart` | ~33 `Future<...Map<String,dynamic>>` shapes |
| `quwoquan_app/lib/cloud/services/rtc/rtc_repository.dart` | ~18 `Future<...Map<String,dynamic>>` shapes |

## 6. Content / Circle / User / Chat 与 service.yaml

详细 API 级缺口表应随 PR 在 `contracts/metadata/<domain>/.../service.yaml` 与 `Abstract *Repository` 之间做 diff；本脚本仅提供 **service.yaml 文件总数** 与 **Repository 粗检** 作为索引。

## 7. 页面门禁 C（64 路径）

规范: `specs/gates/session_c_page_typing.md`

命令:

```bash
python3 scripts/verify_page_abc_governance.py --enforce-c
# 或
make verify-app-page-abc-governance
```

### 本次运行结果

- **exit code**: `0` (0 = pass)
- **tail**:

```
verify_page_abc_governance: paths=64 raw_A=0 raw_B=0 raw_C=0 fail_A=0 fail_B=0 fail_C=0 B_riverpod_only=0

```


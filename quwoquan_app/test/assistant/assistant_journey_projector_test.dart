import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_journey_projector.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/process_trace_event.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

void main() {
  group('AssistantJourneyProjector', () {
    test('thinkingProgress 的拼音检索碎片不进入用户抽屉', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: 'shen zhen tian qi',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'phase': 'analyzing',
            'streaming': true,
            'extracted': true,
          },
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.analyze)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, isEmpty);
      expect(journey.summary, isEmpty);
    });

    test('理解阶段的模板化确认句不会进入用户抽屉', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '我先确认你更在意的是今天出门会不会被雨淋到。',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'phase': 'understanding',
            'streaming': true,
            'extracted': true,
          },
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.analyze)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, isEmpty);
    });

    test('理解阶段的内部规划口吻不会再合成为固定确认句', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '用户想了解深圳天气，我需要搜索最新的天气信息。',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'phase': 'understanding',
            'streaming': true,
            'extracted': true,
          },
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.analyze)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, isEmpty);
    });

    test('检索阶段 trace thinkingProgress 会进入用户抽屉', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '我先换几个检索词继续找',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'phase': 'search', 'streaming': true},
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.search)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, isNotEmpty);
      expect(journey.entries.first.headline, contains('我先换几个检索词继续找'));
    });

    test('searchQueryGenerated 会把检索设计投影为用户可见 search 过程', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchQueryGenerated,
          message: '我先按最影响结论的几路信息分开核对。',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'toolName': 'web_search',
            'query': '深圳天气',
            'searchPlans': <Map<String, dynamic>>[
              <String, dynamic>{'label': '实时天气', 'query': '深圳天气 实时 降雨 温度'},
              <String, dynamic>{'label': '出行影响', 'query': '深圳天气 出行 影响 路况'},
            ],
          },
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.search)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, hasLength(1));
      expect(journey.entries.first.headline, isEmpty);
      expect(journey.entries.first.detail, contains('- 实时天气'));
      expect(journey.entries.first.detail, contains('- 出行影响'));
      expect(journey.entries.first.detail, isNot(contains('深圳天气 实时 降雨 温度')));
    });

    test('answerDelta 只驱动答案主线，不把最终答案正文写进抽屉', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.answerDelta,
          message: '## 深圳今日天气',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'delta': '## 深圳今日天气'},
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.answer)?.status,
        JourneyStageStatus.active,
      );
      expect(journey.entries, isEmpty);
      expect(journey.summary, isEmpty);
    });

    test('suppressed tool error 与技术异常文本不进入用户抽屉', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message:
              'System context failed: MissingPluginException(No implementation found for method getSystemContext on channel personalassistant/nativeapi)',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'toolName': 'system_context',
            'suppressed': true,
          },
        ),
      );

      expect(
        journey.stageFor(JourneyStageId.analyze)?.status,
        JourneyStageStatus.pending,
      );
      expect(journey.entries, isEmpty);
      expect(journey.summary, isEmpty);
    });

    test('synthetic process trace 会按稳定 snapshot 投影为过程块', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      final journey = projector.consumeTrace(
        buildSyntheticProcessTrace(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          stageId: JourneyStageId.search,
          runId: 'run_synthetic_process',
          traceId: 'trace_synthetic_process',
          message: '我先把检索结果里真正有用的点筛出来。',
          payload: const <String, dynamic>{
            'headline': '我先把检索结果里真正有用的点筛出来。',
            'detail': '深圳今天有雨。\n外出建议带伞。',
            'summary': '已筛出 2 条关键点。',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气预报',
                'url': 'https://example.com/weather',
                'source': '官方',
              },
            ],
          },
        ),
      );

      expect(journey.summary, '已筛出 2 条关键点。');
      final searchEntry = journey.entries.firstWhere(
        (entry) => entry.stageId == JourneyStageId.search,
      );
      expect(searchEntry.headline, '我先把检索结果里真正有用的点筛出来。');
      expect(searchEntry.detail, contains('深圳今天有雨'));
      expect(searchEntry.references, hasLength(1));
      expect(searchEntry.references.first.url, 'https://example.com/weather');
    });

    test('process user event 会驱动 canonical journey 过程块', () {
      final projector = AssistantJourneyProjector(
        toolMetadataRegistry: ToolMetadataRegistry(),
      );

      projector.consumeUserEvent(
        const UserEvent(
          type: UserEventType.processReplace,
          scope: UserEventScope.root,
          message: '我先确认你的问题边界。',
          payload: <String, dynamic>{'stageId': 'analyze'},
        ),
      );
      final journey = projector.consumeUserEvent(
        const UserEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.aggregation,
          message: '已核对 2 个来源。',
          payload: <String, dynamic>{
            'stageId': 'search',
            'summary': '已核对 2 个来源。',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '中国气象局',
                'url': 'https://weather.cma.cn/',
                'source': '官方',
              },
              <String, dynamic>{
                'title': '深圳天气',
                'url': 'https://example.com/shenzhen-weather',
                'source': '站点',
              },
            ],
          },
        ),
      );

      expect(journey.summary, '已核对 2 个来源。');
      expect(
        journey.entries.any(
          (entry) =>
              entry.stageId == JourneyStageId.search &&
              entry.references.length == 2,
        ),
        isTrue,
      );
      final searchStage = journey.stages.firstWhere(
        (stage) => stage.stageId == JourneyStageId.search,
      );
      expect(searchStage.status, JourneyStageStatus.completed);
      expect(searchStage.referenceCount, 2);
    });
  });
}

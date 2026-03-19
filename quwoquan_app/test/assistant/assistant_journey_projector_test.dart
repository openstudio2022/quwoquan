import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_journey_projector.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
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

    test('理解阶段的用户语言流式会进入用户抽屉', () {
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
      expect(journey.entries, isNotEmpty);
      expect(journey.entries.first.headline, contains('我先确认你更在意的是今天出门会不会被雨淋到'));
    });

    test('理解阶段的内部规划口吻不会进入用户抽屉', () {
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
      expect(journey.summary, isEmpty);
    });

    test('检索阶段 trace thinkingProgress 只切换阶段，不把模型思维流写进用户抽屉', () {
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
      expect(journey.entries, isEmpty);
      expect(journey.summary, isEmpty);
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
              'Local context failed: MissingPluginException(No implementation found for method getLocalContext on channel personalassistant/nativeapi)',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'toolName': 'local_context',
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

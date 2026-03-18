import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_journey_projector.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

void main() {
  group('AssistantJourneyProjector', () {
    test('thinkingProgress 的 extracted reasoning 不进入用户可见 journey', () {
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

      expect(journey.stageFor(JourneyStageId.analyze)?.status, JourneyStageStatus.active);
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
        journey.entries.any((entry) => entry.headline == '我先确认你的问题边界。'),
        isTrue,
      );
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

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_projection.dart';

void main() {
  group('assistant_process_projection', () {
    test('缺少 uiExplainableFlow 时可从 processJournal 恢复阶段视图', () {
      final message = <String, dynamic>{
        'runArtifacts': <String, dynamic>{
          'processJournal': <Map<String, dynamic>>[
            ProcessJournalEvent(
              eventId: 'journal.execute.1',
              type: ProcessJournalEventType.sourceUpdate,
              stage: 'searching',
              phaseId: 'searching',
              actionCode: 'tool_search',
              reasonCode: 'evidence_gathered',
              reasonShort: '我在核对最新资料',
              message: '我在核对最新资料',
              references: const <ProcessSourceReference>[
                ProcessSourceReference(
                  title: '九寨沟景区公告',
                  url: 'https://example.com/jiuzhaigou',
                  source: '官方',
                ),
              ],
            ).toJson(),
          ],
        },
      };

      final flow = buildExplainableFlowFromMessage(message);

      expect(flow, hasLength(1));
      expect(flow.first.phaseId, PhaseId.execute);
      expect(flow.first.phaseStatus, ExplainablePhaseStatus.completed);
      expect(flow.first.headline, '我在核对最新资料');
      expect(flow.first.references, hasLength(1));
    });

    test('缺少 journal 时可从 uiProcessTimeline 恢复阶段视图', () {
      final message = <String, dynamic>{
        'uiProcessTimeline': <Map<String, dynamic>>[
          <String, dynamic>{
            'scope': 'aggregation',
            'type': 'processCommit',
            'nodeId': 'timeline.0',
            'summary': '我把重点条件收拢后准备组织回答',
            'payload': <String, dynamic>{
              'phaseId': 'analyzing',
              'stage': 'analyzing',
            },
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '四川文旅公告',
                'url': 'https://example.com/scenic',
                'source': '官方',
              },
            ],
          },
        ],
      };

      final flow = buildExplainableFlowFromMessage(message);

      expect(flow, hasLength(1));
      expect(flow.first.phaseId, PhaseId.aggregate);
      expect(flow.first.phaseStatus, ExplainablePhaseStatus.completed);
      expect(flow.first.headline, '我把重点条件收拢后准备组织回答');
      expect(flow.first.references, hasLength(1));
    });

    test('历史消息从 uiExplainableFlow 恢复时会自动收口 active 状态', () {
      final message = <String, dynamic>{
        'streaming': false,
        'uiExplainableFlow': <Map<String, dynamic>>[
          <String, dynamic>{
            'phaseId': 'answer',
            'phaseOrder': 2,
            'phaseStatus': 'active',
            'headline': '我在组织最终回答',
            'detail': '',
            'references': const <Map<String, dynamic>>[],
          },
        ],
      };

      final flow = buildExplainableFlowFromMessage(message);

      expect(flow, hasLength(1));
      expect(flow.first.phaseStatus, ExplainablePhaseStatus.completed);
      expect(flow.first.headline, '我在组织最终回答');
    });
  });
}

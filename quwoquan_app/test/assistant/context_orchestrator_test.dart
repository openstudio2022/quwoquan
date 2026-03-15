import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:test/test.dart';

void main() {
  group('PersonalAssistantContextOrchestrator', () {
    const orchestrator = PersonalAssistantContextOrchestrator();

    ContextContinuityPolicy continuity(
      String query, {
      List<Map<String, dynamic>> sessionHistory =
          const <Map<String, dynamic>>[],
    }) {
      return orchestrator.buildContinuityPolicy(
        query: query,
        sessionHistory: sessionHistory,
      );
    }

    test(
      'default continuity stays fresh and does not infer location or memory',
      () {
        final result = orchestrator.assemble(
          query: '今天天气怎么样',
          historySummary: '',
          recalledTexts: const <String>[],
          deviceProfile: 'mobile',
          deviceModel: '',
          deviceOs: '',
          gpsLocation: const <String, dynamic>{},
          contextScopeHint: const <String, dynamic>{},
          continuityPolicy: continuity('今天天气怎么样'),
        );

        expect(result.canEnterDomain, isTrue);
        expect(result.fillTasks, isEmpty);
        expect(result.hasRealtimeNeed, isFalse);
        final gpsLocation = result.contextEnvelope['gpsLocation'] as Map?;
        expect(gpsLocation?['city'], isNull);
      },
    );

    test('query text no longer injects city or realtime hints', () {
      final result = orchestrator.assemble(
        query: '深圳天气最近怎么样',
        historySummary: '',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{},
        contextScopeHint: const <String, dynamic>{},
        continuityPolicy: continuity('深圳天气最近怎么样'),
      );

      expect(result.canEnterDomain, isTrue);
      final gpsLocation = result.contextEnvelope['gpsLocation'] as Map?;
      expect(gpsLocation?.containsKey('city'), isFalse);
      expect(result.hasRealtimeNeed, isFalse);
    });

    test(
      'location scope remains suppressed without typed continuity grant',
      () {
        final result = orchestrator.assemble(
          query: '今天天气怎么样',
          historySummary: '',
          recalledTexts: const <String>[],
          deviceProfile: 'mobile',
          deviceModel: 'iphone',
          deviceOs: 'ios',
          gpsLocation: const <String, dynamic>{'city': '深圳'},
          contextScopeHint: const <String, dynamic>{},
          continuityPolicy: continuity('今天天气怎么样'),
        );

        expect(result.canEnterDomain, isTrue);
        expect(result.fillTasks, isEmpty);
        final gpsLocation = result.contextEnvelope['gpsLocation'] as Map?;
        expect(gpsLocation?.containsKey('city'), isFalse);
      },
    );

    test('returns gap fill only when typed realtime evidence is required', () {
      final assembled = orchestrator.assemble(
        query: '杭州今天天气',
        historySummary: '',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{'city': '杭州'},
        contextScopeHint: const <String, dynamic>{
          'requiresRealtimeEvidence': true,
          'problemClass': 'realtime_info',
        },
        continuityPolicy: continuity('杭州今天天气'),
      );
      final readiness = orchestrator.checkSynthesisReadiness(
        query: '杭州今天天气',
        finalText: '这是一个通用回答',
        hasToolResult: false,
        problemClass: ProblemClass.realtimeInfo.wireName,
        contextAssembly: assembled,
      );

      expect(readiness.ready, isFalse);
      expect(readiness.gapFillTask, isNotNull);
      expect(readiness.gapFillTask!.fillType, equals(ContextFillType.gapFill));
    });

    test('untyped unrelated history stays suppressed by default', () {
      final policy = continuity(
        '土拨鼠观赏最佳时间',
        sessionHistory: const <Map<String, dynamic>>[
          <String, dynamic>{
            'role': 'user',
            'content': '如果把九寨沟方向考虑进去，多给我几个备选方案',
          },
        ],
      );
      final result = orchestrator.assemble(
        query: '土拨鼠观赏最佳时间',
        historySummary: 'user: 如果把九寨沟方向考虑进去，多给我几个备选方案',
        recalledTexts: const <String>['九寨沟方向备选方案：沟口、川主寺、松潘古城'],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{'city': '阿坝州'},
        contextScopeHint: const <String, dynamic>{},
        continuityPolicy: policy,
      );

      final slotFillHints = result.contextEnvelope['slotFillHints'] as Map?;
      expect(policy.allowHistorySummary, isFalse);
      expect(policy.allowLongtermMemory, isFalse);
      expect(policy.allowLocationHints, isFalse);
      expect(slotFillHints?.containsKey('historySummarySnippet'), isFalse);
      expect(slotFillHints?.containsKey('gpsCity'), isFalse);
      expect(
        result.contextEnvelope.containsKey('longtermMemorySummary'),
        isFalse,
      );
    });

    test('typed continuity hint keeps history continuity', () {
      final policy = continuity(
        '那明天呢',
        sessionHistory: const <Map<String, dynamic>>[
          <String, dynamic>{
            'role': 'user',
            'content': '深圳天气怎么样',
            'continuityPolicy': <String, dynamic>{
              'continuityMode': 'explicit_follow_up',
              'explicitContinuation': true,
              'allowHistorySummary': true,
              'allowLocationHints': true,
            },
          },
        ],
      );
      final result = orchestrator.assemble(
        query: '那明天呢',
        historySummary: 'user: 深圳天气怎么样',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{'city': '深圳'},
        contextScopeHint: const <String, dynamic>{},
        continuityPolicy: policy,
      );

      final slotFillHints = result.contextEnvelope['slotFillHints'] as Map?;
      expect(policy.allowHistorySummary, isTrue);
      expect(policy.allowLocationHints, isTrue);
      expect(slotFillHints?['historySummarySnippet'], isNotEmpty);
      expect(slotFillHints?['gpsCity'], equals('深圳'));
    });

    test(
      'typed longterm memory requirement creates fill task when recall missing',
      () {
        final policy = continuity(
          '帮我总结上个月反复聊过的健身安排',
          sessionHistory: const <Map<String, dynamic>>[
            <String, dynamic>{
              'role': 'user',
              'content': '之前的健身计划',
              'continuityPolicy': <String, dynamic>{
                'allowHistorySummary': true,
                'allowLongtermMemory': true,
              },
            },
          ],
        );
        final result = orchestrator.assemble(
          query: '帮我总结上个月反复聊过的健身安排',
          historySummary: 'user: 之前的健身计划',
          recalledTexts: const <String>[],
          deviceProfile: 'mobile',
          deviceModel: 'iphone',
          deviceOs: 'ios',
          gpsLocation: const <String, dynamic>{},
          contextScopeHint: const <String, dynamic>{
            'requiresLongtermMemory': true,
          },
          continuityPolicy: policy,
        );

        expect(policy.allowLongtermMemory, isTrue);
        expect(result.fillTasks, isNotEmpty);
        expect(
          result.fillTasks.first.targetSlot,
          ContextTargetSlot.longtermMemory,
        );
      },
    );
  });
}

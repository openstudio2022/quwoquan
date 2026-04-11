import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:test/test.dart';

import 'assistant_test_fixture_paths.dart';

Map<String, dynamic> _sessionTurnRunArtifacts(String userFacingSummary) {
  final path =
      assistantMetadataFixturePath('wire_session_turn_run_artifacts.json');
  final m = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
  final us = Map<String, dynamic>.from(
    (m['understandingSnapshot'] as Map).cast<String, dynamic>(),
  );
  us['userFacingSummary'] = userFacingSummary;
  return <String, dynamic>{...m, 'understandingSnapshot': us};
}

void main() {
  group('PersonalAssistantContextOrchestrator', () {
    const orchestrator = PersonalAssistantContextOrchestrator();

    ContextContinuityPolicy continuity(
      String query, {
      List<Map<String, dynamic>> sessionHistory =
          const <Map<String, dynamic>>[],
      int recentRoundsLimit = 5,
    }) {
      return orchestrator.buildContinuityPolicy(
        query: query,
        sessionHistory: sessionHistory,
        recentRoundsLimit: recentRoundsLimit,
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

    test('buildContinuityPolicy 优先使用 structured recent rounds 的 user queries', () {
      final policy = continuity(
        '第三问怎么继续',
        recentRoundsLimit: 2,
        sessionHistory: <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': '第一问'},
          <String, dynamic>{
            'role': 'assistant',
            'content': '第一答',
            'id': 'turn_1',
            'runArtifacts': _sessionTurnRunArtifacts('第一轮理解'),
          },
          <String, dynamic>{'role': 'user', 'content': '第二问'},
          <String, dynamic>{
            'role': 'assistant',
            'content': '第二答',
            'id': 'turn_2',
            'runArtifacts': _sessionTurnRunArtifacts('第二轮理解'),
          },
          <String, dynamic>{'role': 'user', 'content': '第三问'},
        ],
      );

      expect(
        policy.referenceQueries,
        equals(const <String>['第二问', '第一问']),
      );
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
        intentGraph: const IntentGraph(
          userGoal: '杭州今天天气',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'weather',
          problemClass: ProblemClass.realtimeInfo,
          requiresExternalEvidence: true,
          mustVerifyClaims: true,
        ),
        queryTasks: const <QueryTask>[
          QueryTask(
            id: 'current_state',
            query: '杭州今天天气 当前状态',
            label: '当前状态',
            dimension: QueryTaskDimension.currentState,
          ),
        ],
      );

      expect(readiness.ready, isFalse);
      expect(readiness.replanTask, isNotNull);
      expect(readiness.replanTask!.fillType, equals(ContextFillType.replan));
    });

    test('tool result 已返回但证据仍为 retry 时继续拦 synthesis', () {
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
        finalText: '这是一个看起来已经能回答的草稿',
        hasToolResult: true,
        problemClass: ProblemClass.realtimeInfo.wireName,
        contextAssembly: assembled,
        intentGraph: const IntentGraph(
          userGoal: '杭州今天天气',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'weather',
          problemClass: ProblemClass.realtimeInfo,
          requiresExternalEvidence: true,
          mustVerifyClaims: true,
        ),
        queryTasks: const <QueryTask>[
          QueryTask(
            id: 'current_state',
            query: '杭州今天天气 当前状态',
            label: '当前状态',
            dimension: QueryTaskDimension.currentState,
          ),
        ],
        evidenceEvaluation: const EvidenceEvaluationResult(
          status: EvidenceStatus.retry,
          passed: false,
          evidenceRequired: true,
          summary: '证据还不够稳，需要继续补一轮。',
        ),
      );

      expect(readiness.ready, isFalse);
      expect(readiness.reason, contains('证据还不够稳'));
      expect(readiness.replanTask, isNotNull);
    });

    test('bounded 证据可放行 synthesis readiness', () {
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
        finalText: '可先回答已确认部分',
        hasToolResult: true,
        problemClass: ProblemClass.realtimeInfo.wireName,
        contextAssembly: assembled,
        intentGraph: const IntentGraph(
          userGoal: '杭州今天天气',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'weather',
          problemClass: ProblemClass.realtimeInfo,
          requiresExternalEvidence: true,
          mustVerifyClaims: true,
        ),
        queryTasks: const <QueryTask>[
          QueryTask(
            id: 'current_state',
            query: '杭州今天天气 当前状态',
            label: '当前状态',
            dimension: QueryTaskDimension.currentState,
          ),
        ],
        evidenceEvaluation: const EvidenceEvaluationResult(
          status: EvidenceStatus.bounded,
          passed: false,
          evidenceRequired: true,
          entries: <EvidenceLedgerEntry>[
            EvidenceLedgerEntry(
              evidenceId: 'weather::current::https://weather.cma.cn/hangzhou',
              title: '杭州天气实况',
              url: 'https://weather.cma.cn/hangzhou',
            ),
          ],
          summary: '已收拢 1 条证据，可以先回答已确认部分。',
        ),
      );

      expect(readiness.ready, isTrue);
    });

    test('bindEvidenceToSlots 会把证据账回写到 slot evidenceIds', () {
      const slotState = SlotStateSnapshot(
        domainId: 'weather',
        slotValues: <String, SlotValueSnapshot>{
          'city': SlotValueSnapshot(
            slotId: 'city',
            value: '深圳',
            source: 'user_query',
          ),
        },
      );
      const ledger = <EvidenceLedgerEntry>[
        EvidenceLedgerEntry(
          evidenceId: 'weather::current::https://weather.cma.cn/shenzhen',
          title: '深圳天气预报 - 中国气象局',
          url: 'https://weather.cma.cn/shenzhen',
          slotContributions: <String, dynamic>{'city': '深圳'},
        ),
      ];

      final bound = orchestrator.bindEvidenceToSlots(
        slotState: slotState,
        evidenceLedger: ledger,
      );

      expect(
        bound.slotValueOf('city')?.evidenceIds,
        contains('weather::current::https://weather.cma.cn/shenzhen'),
      );
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

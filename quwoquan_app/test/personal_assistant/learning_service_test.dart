import 'dart:io';

import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_service.dart';
import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_store.dart';
import 'package:quwoquan_app/personal_assistant/sync/local_mock_sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_gateway.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantLearningService', () {
    test('records interaction and builds user/tag-domain aggregates', () async {
      final file = File('${Directory.systemTemp.path}/learning_service_test_${DateTime.now().microsecondsSinceEpoch}.json');
      final store = AssistantLearningStore(storagePath: file.path);
      final adapter = LocalMockSyncAdapter();
      final gateway = AssistantSyncGateway(adapter, AssistantSyncMode.localMock);
      final service = AssistantLearningService(
        store: store,
        syncGateway: gateway,
      );

      await service.recordInteraction(
        runId: 'run_1',
        traceId: 'trace_1',
        userId: 'user_a',
        sessionId: 'assistant',
        pageType: 'chat',
        queryText: '深圳天气怎么样',
        answerText: '[web] 深圳今日多云，温度 18-24 度',
        userTags: const <String>['creator', 'daily_user'],
        durationMs: 1400,
        explicitThumb: 'up',
        regeneratedAnswer: true,
        styleAdjusted: true,
        modelSwitched: true,
        referenceOpened: true,
      );

      final snapshot = await service.latestScoreSnapshot();
      final userDaily = (snapshot['userDaily'] as List?) ?? const <dynamic>[];
      final tagDomainDaily = (snapshot['tagDomainDaily'] as List?) ?? const <dynamic>[];

      expect(userDaily.isNotEmpty, isTrue);
      expect(tagDomainDaily.isNotEmpty, isTrue);
      expect(adapter.interactionEvents.length, equals(1));
      expect(adapter.scorecards.isNotEmpty, isTrue);
      final feedbackStats =
          (snapshot['feedbackStats'] as Map?) ?? const <String, dynamic>{};
      expect((feedbackStats['regenerateCount'] as int?) ?? 0, equals(1));
      expect((feedbackStats['styleAdjustedCount'] as int?) ?? 0, equals(1));
      expect((feedbackStats['modelSwitchedCount'] as int?) ?? 0, equals(1));
      expect((feedbackStats['referenceOpenedCount'] as int?) ?? 0, equals(1));
    });

    test('records explicit feedback with correction text', () async {
      final file = File(
        '${Directory.systemTemp.path}/learning_feedback_test_${DateTime.now().microsecondsSinceEpoch}.json',
      );
      final store = AssistantLearningStore(storagePath: file.path);
      final adapter = LocalMockSyncAdapter();
      final gateway = AssistantSyncGateway(adapter, AssistantSyncMode.localMock);
      final service = AssistantLearningService(
        store: store,
        syncGateway: gateway,
      );

      await service.recordExplicitFeedback(
        runId: 'run_feedback',
        traceId: 'trace_feedback',
        userId: 'user_a',
        sessionId: 'assistant',
        pageType: 'chat',
        queryText: '深圳天气怎么样',
        answerText: '深圳今天天气不错',
        userTags: const <String>['daily_user'],
        explicitThumb: 'down',
        explicitReasonCodes: const <String>['incorrect'],
        correctionText: '请补充最高最低温和降雨概率',
        feedbackTargetMessageId: 'assistant_1',
      );

      expect(adapter.interactionEvents.length, equals(1));
      final feedback = adapter.interactionEvents.first;
      expect(feedback['correctionText'], isNotEmpty);
      expect(feedback['explicitThumb'], equals('down'));

      final snapshot = await service.latestScoreSnapshot();
      final feedbackStats = (snapshot['feedbackStats'] as Map?) ?? const <String, dynamic>{};
      final reasonDist =
          (feedbackStats['reasonCodeDistribution'] as Map?) ?? const <String, dynamic>{};
      final domainDist =
          (feedbackStats['domainDistribution'] as Map?) ?? const <String, dynamic>{};
      final tagDist =
          (feedbackStats['userTagDistribution'] as Map?) ?? const <String, dynamic>{};
      expect((feedbackStats['explicitTotal'] as int?) ?? 0, greaterThan(0));
      expect(reasonDist.isNotEmpty, isTrue);
      expect(domainDist.isNotEmpty, isTrue);
      expect(tagDist.isNotEmpty, isTrue);
    });
  });
}


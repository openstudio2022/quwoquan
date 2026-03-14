import 'dart:io';

import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_service.dart';
import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_store.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_gateway.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantLearningService', () {
    late Directory tempDir;
    late AssistantLearningStore store;
    late AssistantLearningService service;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp(
        'assistant_learning_service_test_',
      );
      store = AssistantLearningStore(
        storagePath: '${tempDir.path}/learning_store.json',
      );
      service = AssistantLearningService(
        store: store,
        syncGateway: AssistantSyncGateway(
          _FakeSyncAdapter(),
          AssistantSyncMode.localMock,
        ),
      );
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test(
      'prefers explicit metadata hints instead of query text classification',
      () async {
        await service.recordInteraction(
          runId: 'run_1',
          traceId: 'trace_1',
          userId: 'user_1',
          sessionId: 'session_1',
          pageType: 'chat',
          queryText: '今天杭州天气怎么样',
          answerText: '已回答',
          userTags: const <String>['domain:travel_transport'],
          durationMs: 1200,
        );

        final events = await store.events();
        expect(events, hasLength(1));
        expect(events.first.domainId, equals('travel_transport'));
      },
    );

    test(
      'falls back to general when only query text contains domain words',
      () async {
        await service.recordInteraction(
          runId: 'run_2',
          traceId: 'trace_2',
          userId: 'user_2',
          sessionId: 'session_2',
          pageType: 'chat',
          queryText: '帮我看看天气和机票',
          answerText: '已回答',
          userTags: const <String>[],
          durationMs: 800,
        );

        final events = await store.events();
        expect(events, hasLength(1));
        expect(events.first.domainId, equals('general'));
      },
    );
  });
}

class _FakeSyncAdapter implements AssistantSyncAdapter {
  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return const AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.policy,
      message: 'ok',
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    return const AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.interactionEvents,
      message: 'ok',
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    return const AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.scorecards,
      message: 'ok',
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    return const AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.memoryRecords,
      message: 'ok',
    );
  }
}

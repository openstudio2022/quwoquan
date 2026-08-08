// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/assistant_history_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show actorQueueStorageProvider;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/actor_queue/actor_queue_test_storage.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/controllable_assistant_run_facets.dart';
import '../../../../../support/service/notification_service/notification_delivery/notification/app_message_typed_double.dart';

void main() {
  group('PersonalAssistantRun concurrency', () {
    test(
      'nonterminal app message resumes same run after maximum sequence',
      () async {
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[
            assistantRunStreamEventFixture(seq: 1, eventType: 'run_started'),
            assistantRunStreamEventFixture(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '正在核对天气'},
            ),
          ],
        );
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await notifier.send('规划明天的西湖行程');
        expect(
          container.read(personalAssistantStreamControllerProvider).events,
          hasLength(2),
        );
        repository.getRunResult = const AssistantRunEnvelopeWire(
          runId: 'arn_test_personal',
          sessionId: 'asn_test_personal',
          status: 'executing',
          goal: '规划明天的西湖行程',
          traceId: 'trace_test',
          createdAt: '2026-04-29T00:00:00Z',
        );
        repository.events.add(
          assistantRunStreamEventFixture(
            seq: 3,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '西湖行程已按天气调整完成'},
          ),
        );

        await notifier.openRunFromAppMessage('arn_test_personal');

        final resumed = container.read(
          personalAssistantStreamControllerProvider,
        );
        expect(repository.streamResumeTokens.last, '2');
        expect(resumed.answer, '西湖行程已按天气调整完成');
        expect(resumed.events.map((event) => event.seq), <int>[1, 2, 3]);
        expect(resumed.runStatus, 'completed');
        expect(resumed.running, isFalse);
        expect(resumed.errorMessage, isEmpty);
      },
    );

    test(
      'steer reports success only after canonical control receipt',
      () async {
        final eventStream = StreamController<AssistantStreamEventWire>();
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[],
          eventStream: eventStream.stream,
        );
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );
        final sendFuture = notifier.send('规划周末杭州行程');
        await pumpEventQueue();
        eventStream.add(
          assistantRunStreamEventFixture(seq: 1, eventType: 'run_started'),
        );
        await pumpEventQueue();

        expect(await notifier.steerCurrentRun('不要安排得太赶'), isTrue);
        expect(repository.steerInstructions, <String>['不要安排得太赶']);

        repository.steerError = StateError('steer unavailable (test)');
        expect(await notifier.steerCurrentRun('预算控制在一千元'), isFalse);
        expect(
          container
              .read(personalAssistantStreamControllerProvider)
              .errorMessage,
          isNotEmpty,
        );

        eventStream.add(
          assistantRunStreamEventFixture(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '杭州行程已完成'},
          ),
        );
        await eventStream.close();
        await sendFuture;
      },
    );

    test(
      'app message generation cancels an older send stream and rejects late events',
      () async {
        final oldStream = StreamController<AssistantStreamEventWire>();
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[],
          eventStream: oldStream.stream,
          getRunResult: const AssistantRunEnvelopeWire(
            runId: 'arn_app_message_new',
            sessionId: 'asn_app_message_new',
            status: 'completed',
            goal: '打开后台任务',
            terminalSnapshot: AssistantRunTerminalSnapshotView(
              answerText: '后台任务已经完成。',
              processes: <AssistantRunVisibleProcessView>[],
            ),
            traceId: 'trace_app_message_new',
            createdAt: '2026-08-08T00:00:00Z',
            completedAt: '2026-08-08T00:01:00Z',
          ),
        );
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        final oldSend = notifier.send('旧任务');
        await pumpEventQueue();
        oldStream.add(
          assistantRunStreamEventFixture(seq: 1, eventType: 'run_started'),
        );
        await pumpEventQueue();

        await notifier.openRunFromAppMessage('arn_app_message_new');
        oldStream.add(
          assistantRunStreamEventFixture(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '旧任务晚到答案'},
          ),
        );
        await oldStream.close();
        await oldSend;

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.runId, 'arn_app_message_new');
        expect(state.sessionId, 'asn_app_message_new');
        expect(state.answer, '后台任务已经完成。');
        expect(state.answer, isNot(contains('旧任务晚到答案')));
        expect(state.running, isFalse);
      },
    );

    test(
      'newer app message wins when GetRun responses arrive out of order',
      () async {
        final slow = Completer<AssistantRunEnvelopeWire>();
        final fast = Completer<AssistantRunEnvelopeWire>();
        final repository =
            ControllableAssistantRunFacets(events: <AssistantStreamEventWire>[])
              ..getRunCompleters['arn_slow'] = slow
              ..getRunCompleters['arn_fast'] = fast;
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        final slowOpen = notifier.openRunFromAppMessage('arn_slow');
        await pumpEventQueue();
        final fastOpen = notifier.openRunFromAppMessage('arn_fast');
        fast.complete(
          const AssistantRunEnvelopeWire(
            runId: 'arn_fast',
            sessionId: 'asn_fast',
            status: 'completed',
            goal: '新通知',
            terminalSnapshot: AssistantRunTerminalSnapshotView(
              answerText: '新通知答案',
              processes: <AssistantRunVisibleProcessView>[],
            ),
            traceId: 'trace_fast',
            createdAt: '2026-08-08T00:00:00Z',
            completedAt: '2026-08-08T00:01:00Z',
          ),
        );
        await fastOpen;
        slow.complete(
          const AssistantRunEnvelopeWire(
            runId: 'arn_slow',
            sessionId: 'asn_slow',
            status: 'completed',
            goal: '旧通知',
            terminalSnapshot: AssistantRunTerminalSnapshotView(
              answerText: '旧通知晚到答案',
              processes: <AssistantRunVisibleProcessView>[],
            ),
            traceId: 'trace_slow',
            createdAt: '2026-08-08T00:00:00Z',
            completedAt: '2026-08-08T00:01:00Z',
          ),
        );
        await slowOpen;

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.runId, 'arn_fast');
        expect(state.answer, '新通知答案');
        expect(state.answer, isNot(contains('旧通知晚到答案')));
      },
    );

    test(
      'replacement app message cancels a continued run stream generation',
      () async {
        final continuedStream = StreamController<AssistantStreamEventWire>();
        final repository =
            ControllableAssistantRunFacets(events: <AssistantStreamEventWire>[])
              ..getRunResults['arn_continued'] = const AssistantRunEnvelopeWire(
                runId: 'arn_continued',
                sessionId: 'asn_continued',
                status: 'executing',
                goal: '继续后台任务',
                traceId: 'trace_continued',
                createdAt: '2026-08-08T00:00:00Z',
              )
              ..getRunResults['arn_replacement'] =
                  const AssistantRunEnvelopeWire(
                    runId: 'arn_replacement',
                    sessionId: 'asn_replacement',
                    status: 'completed',
                    goal: '替换任务',
                    terminalSnapshot: AssistantRunTerminalSnapshotView(
                      answerText: '替换任务答案',
                      processes: <AssistantRunVisibleProcessView>[],
                    ),
                    traceId: 'trace_replacement',
                    createdAt: '2026-08-08T00:00:00Z',
                    completedAt: '2026-08-08T00:01:00Z',
                  )
              ..eventStreamsByRunId['arn_continued'] = continuedStream.stream;
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        final continuedOpen = notifier.openRunFromAppMessage('arn_continued');
        await pumpEventQueue();
        continuedStream.add(
          assistantRunStreamEventFixture(
            seq: 1,
            eventType: 'run_started',
            runId: 'arn_continued',
            sessionId: 'asn_continued',
          ),
        );
        await pumpEventQueue();

        await notifier.openRunFromAppMessage('arn_replacement');
        continuedStream.add(
          assistantRunStreamEventFixture(
            seq: 2,
            eventType: 'completed',
            runId: 'arn_continued',
            sessionId: 'asn_continued',
            payload: const <String, dynamic>{'text': '旧续跑晚到答案'},
          ),
        );
        await continuedStream.close();
        await continuedOpen;

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.runId, 'arn_replacement');
        expect(state.answer, '替换任务答案');
        expect(state.answer, isNot(contains('旧续跑晚到答案')));
      },
    );

    test(
      'continued run resumes an uncommitted presentation and preserves the core answer',
      () async {
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[
            assistantRunStreamEventFixture(
              seq: 1,
              eventType: 'presentation_snapshot',
              payload: <String, dynamic>{
                'baseRevision': 0,
                'revision': 1,
                'document': _presentationDocumentJson(revision: 1),
              },
            ),
            assistantRunStreamEventFixture(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '正在生成旅行展示'},
            ),
          ],
        );
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await notifier.send('继续生成旅行展示');
        repository.getRunResult = const AssistantRunEnvelopeWire(
          runId: 'arn_test_personal',
          sessionId: 'asn_test_personal',
          status: 'executing',
          goal: '继续生成旅行展示',
          traceId: 'trace_test',
          createdAt: '2026-08-08T00:00:00Z',
        );
        repository.events.addAll(<AssistantStreamEventWire>[
          assistantRunStreamEventFixture(
            seq: 3,
            eventType: 'presentation_commit',
            payload: const <String, dynamic>{
              'baseRevision': 1,
              'revision': 2,
              'committedAt': '2026-08-08T00:00:02Z',
            },
          ),
          assistantRunStreamEventFixture(
            seq: 4,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '旅行展示与核心答案均已恢复。'},
          ),
        ]);

        await notifier.openRunFromAppMessage('arn_test_personal');

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.runStatus, 'completed');
        expect(state.answer, '旅行展示与核心答案均已恢复。');
        expect(state.errorMessage, isEmpty);
        final assistantRow = state.transcript
            .whereType<AssistantAnswerTranscriptRow>()
            .lastWhere((row) => row.anchor.runId == 'arn_test_personal');
        final document = AssistantPresentationDocumentWire.fromJson(
          (assistantRow.runArtifacts['presentationDocument'] as Map)
              .cast<String, dynamic>(),
        );
        expect(document.revision, 2);
        expect(document.committedAt, '2026-08-08T00:00:02Z');
      },
    );

    test(
      'invalid continued presentation event degrades without failing the run',
      () async {
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[
            assistantRunStreamEventFixture(
              seq: 1,
              eventType: 'presentation_snapshot',
              payload: <String, dynamic>{
                'baseRevision': 7,
                'revision': 1,
                'document': _presentationDocumentJson(revision: 1),
              },
            ),
            assistantRunStreamEventFixture(
              seq: 2,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '坏展示已降级，核心答案仍完成。'},
            ),
          ],
          getRunResult: const AssistantRunEnvelopeWire(
            runId: 'arn_invalid_presentation',
            sessionId: 'asn_invalid_presentation',
            status: 'executing',
            goal: '恢复坏展示事件',
            traceId: 'trace_invalid_presentation',
            createdAt: '2026-08-08T00:00:00Z',
          ),
        );
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await notifier.openRunFromAppMessage('arn_invalid_presentation');

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.runId, 'arn_invalid_presentation');
        expect(state.runStatus, 'completed');
        expect(state.answer, '坏展示已降级，核心答案仍完成。');
        expect(state.running, isFalse);
        expect(state.errorMessage, isEmpty);
      },
    );

    test(
      'steer response-lost retry reuses identity and edited intent rotates it',
      () async {
        final eventStream = StreamController<AssistantStreamEventWire>();
        final repository = ControllableAssistantRunFacets(
          events: <AssistantStreamEventWire>[],
          eventStream: eventStream.stream,
        )..steerFailuresAfterAcceptRemaining = 1;
        final container = _containerWith(repository);
        addTearDown(container.dispose);
        final notifier = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );
        final sendFuture = notifier.send('规划杭州行程');
        await pumpEventQueue();
        eventStream.add(
          assistantRunStreamEventFixture(seq: 1, eventType: 'run_started'),
        );
        await pumpEventQueue();

        expect(await notifier.steerCurrentRun('不要安排得太赶'), isFalse);
        expect(await notifier.steerCurrentRun('不要安排得太赶'), isTrue);
        expect(repository.steerCommandRequestIds, hasLength(2));
        expect(
          repository.steerCommandRequestIds[0],
          repository.steerCommandRequestIds[1],
        );

        repository.steerFailuresAfterAcceptRemaining = 1;
        expect(await notifier.steerCurrentRun('预算控制在一千元'), isFalse);
        expect(await notifier.steerCurrentRun('预算控制在一千元'), isTrue);
        expect(repository.steerCommandRequestIds, hasLength(4));
        expect(
          repository.steerCommandRequestIds[2],
          isNot(repository.steerCommandRequestIds[0]),
        );
        expect(
          repository.steerCommandRequestIds[2],
          repository.steerCommandRequestIds[3],
        );

        eventStream.add(
          assistantRunStreamEventFixture(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '杭州行程已完成'},
          ),
        );
        await eventStream.close();
        await sendFuture;
      },
    );

    test('late steer receipt cannot overwrite a replacement run', () async {
      final eventStream = StreamController<AssistantStreamEventWire>();
      final steerReceipt = Completer<AssistantRunEnvelopeWire>();
      final repository = ControllableAssistantRunFacets(
        events: <AssistantStreamEventWire>[],
        eventStream: eventStream.stream,
      )..steerResponseCompleter = steerReceipt;
      final container = _containerWith(repository);
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      final sendFuture = notifier.send('规划杭州行程');
      await pumpEventQueue();
      eventStream.add(
        assistantRunStreamEventFixture(seq: 1, eventType: 'run_started'),
      );
      await pumpEventQueue();

      final steerFuture = notifier.steerCurrentRun('增加一个博物馆');
      await pumpEventQueue();
      repository.getRunResult = const AssistantRunEnvelopeWire(
        runId: 'arn_replacement_after_steer',
        sessionId: 'asn_replacement_after_steer',
        status: 'completed',
        goal: '替换任务',
        terminalSnapshot: AssistantRunTerminalSnapshotView(
          answerText: '替换任务保持当前状态',
          processes: <AssistantRunVisibleProcessView>[],
        ),
        traceId: 'trace_replacement_after_steer',
        createdAt: '2026-08-08T00:00:00Z',
        completedAt: '2026-08-08T00:01:00Z',
      );
      await notifier.openRunFromAppMessage('arn_replacement_after_steer');
      steerReceipt.complete(
        const AssistantRunEnvelopeWire(
          runId: 'arn_test_personal',
          sessionId: 'asn_test_personal',
          status: 'executing',
          traceId: 'trace_test',
          createdAt: '2026-08-08T00:00:00Z',
        ),
      );
      expect(await steerFuture, isFalse);
      await eventStream.close();
      await sendFuture;

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.runId, 'arn_replacement_after_steer');
      expect(state.answer, '替换任务保持当前状态');
      expect(state.runStatus, 'completed');
      expect(state.errorMessage, isEmpty);
    });

    test('run controller and focused partitions stay below source budgets', () {
      final limits = <String, int>{
        'lib/service/assistant_service/assistant/assistant_run/application/'
                'personal_assistant_stream_controller.dart':
            1000,
        'lib/service/assistant_service/assistant/assistant_run/application/'
                'personal_assistant_stream_controller_run_lifecycle.dart':
            1000,
        'test/local_contract/service/assistant_service/assistant/assistant_run/'
                'personal_assistant_stream_controller__local_contract_test.dart':
            2245,
        'test/local_contract/service/assistant_service/assistant/assistant_run/'
                'personal_assistant_run_concurrency__local_contract_test.dart':
            1000,
        'test/support/service/assistant_service/assistant/assistant_run/'
                'controllable_assistant_run_facets.dart':
            1000,
      };

      for (final entry in limits.entries) {
        final file = File(entry.key);
        expect(file.existsSync(), isTrue, reason: entry.key);
        expect(
          file.readAsLinesSync().length,
          lessThan(entry.value),
          reason: entry.key,
        );
      }
    });
  });
}

ProviderContainer _containerWith(ControllableAssistantRunFacets repository) {
  return ProviderContainer(
    overrides: [
      ...assistantFacetOverrides(repository),
      actorQueueStorageProvider.overrideWithValue(newTestActorQueueStorage()),
      assistantLearningFactOutboxEnvironmentProvider.overrideWithValue('alpha'),
      currentUserIdProvider.overrideWithValue('persona_test'),
      resolvedOwnerUserIdProvider.overrideWithValue('user_test'),
      appMessageQueryProvider.overrideWithValue(
        const EmptyAppMessageQueryDouble(),
      ),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          personaId: 'persona_test',
          ownerUserId: 'user_test',
          displayName: '测试分身',
          avatarUrl: '',
        ),
      ),
      assistantHistoryLoaderProvider.overrideWithValue(
        const EmptyAssistantHistoryLoader(),
      ),
    ],
  );
}

Map<String, dynamic> _presentationDocumentJson({required int revision}) {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  return <String, dynamic>{
    'templateRef': 'assistant.timeline@$digest',
    'templateDigest': digest,
    'revision': revision,
    'rootNodeId': 'root',
    'nodes': <Map<String, dynamic>>[
      <String, dynamic>{
        'nodeId': 'root',
        'parentNodeId': '',
        'order': 0,
        'kind': 'timeline',
        'title': '旅行时间线',
        'body': '旅行展示正文',
        'data': const <String, dynamic>{},
        'binding': const <String, dynamic>{},
        'style': const <String, dynamic>{},
        'accessibility': const <String, dynamic>{},
      },
    ],
    'dataDigest': digest,
    'selectedVariant': 'compact',
    'fallbackMarkdown': '旅行展示降级正文',
    'fallbackPlainText': '旅行展示降级正文',
    'committedAt': '',
  };
}

// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/persisted_assistant_turn.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_presentation_action_dispatcher.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show actorQueueStorageProvider;
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/platform/device_calendar_bridge.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/presentation/assistant_skill_center_page.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/assistant_history_loader.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_history.dart';
import 'package:quwoquan_app/runtime/di/assistant_history_dependencies.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/regenerate_options_popup.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/runtime/transport/actor_queue/actor_queue_test_storage.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_scenario_fixtures.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

late ActorQueueStorage _actorQueueStorage;

class _EmptyAssistantHistoryLoader implements AssistantHistoryLoader {
  const _EmptyAssistantHistoryLoader();

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async {
    return null;
  }
}

void main() {
  late Directory hiveDirectory;

  setUp(() async {
    hiveDirectory = Directory.systemTemp.createTempSync(
      'qwq_assistant_learning_controller_',
    );
    Hive.init(hiveDirectory.path);
    _actorQueueStorage = newTestActorQueueStorage();
  });

  tearDown(() async {
    await Hive.close();
    if (await hiveDirectory.exists()) {
      await hiveDirectory.delete(recursive: true);
    }
  });

  group('PersonalAssistantStreamController', () {
    test('显式 alpha facet override 投影 scenario stream', () async {
      final scenarioPack = loadAssistantScenarioPack();
      final scenario = scenarioPack
          .assistantTurnScenariosFor('alpha')
          .firstWhere((item) => item.id == 'weather_trip_basic');
      final container = ProviderContainer(
        overrides: [
          ...assistantFacetOverrides(
            ScenarioMockAssistantRepository(pack: scenarioPack),
          ),
          assistantHistoryLoaderProvider.overrideWithValue(
            const _EmptyAssistantHistoryLoader(),
          ),
          actorQueueStorageProvider.overrideWithValue(_actorQueueStorage),
          assistantLearningFactOutboxEnvironmentProvider.overrideWithValue(
            'alpha',
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(
        container.read(assistantSessionRunFacetProvider),
        isA<InMemoryAssistantFacets>(),
      );

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question);

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.runId, 'arn_fixture_${scenario.id}');
      expect(state.answer, scenario.alphaMockStream.finalAnswer);
      expect(state.transcript, hasLength(2));
      expect(state.transcript.first, isA<UserTranscriptTimelineRow>());
      expect(state.transcript.last, isA<AssistantAnswerTranscriptRow>());
      expect(state.errorMessage, isEmpty);
      expect(
        state.events.map((event) => event.eventType.wireName),
        containsAll(scenario.expectedEvents),
      );
    });

    test('projects typed stream and ignores duplicate seq', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '你好，'},
            ),
            _event(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '重复'},
            ),
            _event(
              seq: 1,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '乱序'},
            ),
            _event(
              seq: 3,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '你好，我是找私助。'},
            ),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('安排今天');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.answer, '你好，我是找私助。');
      expect(state.errorMessage, isEmpty);
      expect(state.transcript.map((item) => item.runtimeType), <Type>[
        UserTranscriptTimelineRow,
        AssistantAnswerTranscriptRow,
      ]);
      final assistantRow =
          state.transcript.last as AssistantAnswerTranscriptRow;
      expect(assistantRow.content, '你好，我是找私助。');
      expect(assistantRow.streaming, isFalse);
      expect(state.events.map((event) => event.seq), <int>[1, 2, 3]);
      expect(state.sessionId, 'asn_test_personal');
      expect(state.runId, 'arn_test_personal');
    });

    test(
      'retries one command identity without creating a second session',
      () async {
        final repository = _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '重试成功'},
            ),
          ],
        )..startRunFailuresRemaining = 1;
        final container = _containerWith(assistantRepository: repository);
        addTearDown(container.dispose);
        final controller = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await controller.send('幂等重试');
        expect(
          container
              .read(personalAssistantStreamControllerProvider)
              .retryAvailable,
          isTrue,
        );

        await controller.retryLastFailedAction();

        expect(repository.createdSessionRequestIds, hasLength(1));
        expect(repository.startedRunClientRequestIds, hasLength(2));
        expect(repository.startedRunClientRequestIds.toSet(), hasLength(1));
        expect(
          container.read(personalAssistantStreamControllerProvider).sessionId,
          'asn_test_personal',
        );
        expect(
          container
              .read(personalAssistantStreamControllerProvider)
              .errorMessage,
          isEmpty,
        );
      },
    );

    test(
      'retries an unacknowledged session creation with the same intent',
      () async {
        final repository = _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '会话重试成功'},
            ),
          ],
        )..createSessionFailuresRemaining = 1;
        final container = _containerWith(assistantRepository: repository);
        addTearDown(container.dispose);
        final controller = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await controller.send('创建会话重试');
        expect(
          container
              .read(personalAssistantStreamControllerProvider)
              .retryAvailable,
          isTrue,
        );

        await controller.retryLastFailedAction();

        expect(repository.createdSessionRequestIds, hasLength(2));
        expect(repository.createdSessionRequestIds.toSet(), hasLength(1));
        expect(repository.startedRunClientRequestIds, hasLength(1));
        expect(
          container.read(personalAssistantStreamControllerProvider).sessionId,
          'asn_test_personal',
        );
        expect(
          container
              .read(personalAssistantStreamControllerProvider)
              .errorMessage,
          isEmpty,
        );
      },
    );

    test('交集入口只向下一次 StartAssistantRun 提交强类型证据引用', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(seq: 1, eventType: 'run_started'),
          _event(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '已按交集说明。'},
          ),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      controller.setOpenContext(
        AssistantOpenContext(
          source: AssistantSource.profile,
          entityId: 'post-1',
          objectType: 'post',
          experienceLevel: AssistantExperienceLevel.returning,
          intersectionEvidenceRefs: const <AssistantIntersectionEvidenceRef>[
            AssistantIntersectionEvidenceRef(
              intersectionId: 'intersection-1',
              evidenceId: 'snapshot-1',
              sourceRef: 'same_school',
              objectTypeRef: 'content.post',
              objectId: 'post-1',
            ),
          ],
        ),
      );

      await controller.send('解释这条交集');

      expect(repository.startedIntersectionEvidenceRefs, hasLength(1));
      expect(
        repository.startedIntersectionEvidenceRefs.single.evidenceId,
        'snapshot-1',
      );
      expect(
        repository.startedIntersectionEvidenceRefs.single.objectId,
        'post-1',
      );
    });

    test('完整会话入口在首个 StartAssistantRun 前上报同一份页面上下文', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(seq: 1, eventType: 'run_started'),
          _event(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '已整理页面上下文。'},
          ),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      controller.setOpenContext(
        const AssistantOpenContext(
          source: AssistantSource.search,
          entityId: 'query-001',
          objectType: 'search.query',
          experienceLevel: AssistantExperienceLevel.returning,
        ),
      );

      await controller.send('帮我解释当前搜索结果');

      expect(
        repository.callOrder,
        containsAllInOrder(<String>['reportPageContext', 'startAssistantRun']),
      );
      expect(repository.reportedPageContext?.source, AssistantSource.search);
      expect(repository.reportedPageContextActions, <String>[
        'open_assistant_session',
      ]);
    });

    test('页面上下文上报失败时完整会话不得启动 Run', () async {
      final repository = _FakeAssistantRepository(
        events: const <AssistantStreamEventWire>[],
      )..failPageContextReport = true;
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      controller.setOpenContext(
        const AssistantOpenContext(
          source: AssistantSource.article,
          entityId: 'post-001',
          objectType: 'content.post',
          experienceLevel: AssistantExperienceLevel.returning,
        ),
      );

      await controller.send('解释当前内容');

      expect(repository.startedRunTexts, isEmpty);
      expect(
        container.read(personalAssistantStreamControllerProvider).errorMessage,
        isNotEmpty,
      );
    });

    test('终态流按目录化 assistant_turn_quality 上报全链路质量', () async {
      final telemetry = RecordingAppTelemetryRecorder();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '正在整理'},
            ),
            _event(
              seq: 3,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '整理完成'},
            ),
          ],
        ),
        telemetryRecorder: telemetry,
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('请整理');
      await Future<void>.delayed(Duration.zero);

      expect(
        telemetry.recorded.map((event) => event.eventType),
        everyElement('assistant_turn_quality'),
      );
      expect(
        telemetry.recorded
            .map((event) => event.extensions['turnAction'])
            .toList(),
        <String>['submit', 'first_answer', 'completed'],
      );
      expect(
        telemetry.recorded.map((event) => event.extensions['result']).toList(),
        <String>['success', 'success', 'success'],
      );
      expect(
        telemetry.recorded
            .map((event) => event.extensions['operationId'])
            .toSet(),
        containsAll(<String>{'StartAssistantRun', 'StreamAssistantRunEvents'}),
      );
    });

    test('restarted run_started 清空重启前的回答增量', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '旧回答'},
            ),
            _event(
              seq: 2,
              eventType: 'run_started',
              payload: const <String, dynamic>{'restarted': true},
            ),
            _event(seq: 3, eventType: 'completed'),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('重新执行');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.answer, isEmpty);
      final assistantRow =
          state.transcript.last as AssistantAnswerTranscriptRow;
      expect(assistantRow.content, isEmpty);
      expect(assistantRow.streaming, isFalse);
    });

    test(
      'restores stored transcript before continuing personal assistant turns',
      () async {
        final historyLoader = _FakeAssistantHistoryLoader(
          snapshot: await _buildAssistantHistorySnapshot(),
        );
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(
                seq: 1,
                eventType: 'completed',
                payload: const <String, dynamic>{'text': '你好，我是找私助。'},
              ),
            ],
          ),
          historyLoader: historyLoader,
        );
        addTearDown(container.dispose);

        await container
            .read(personalAssistantStreamControllerProvider.notifier)
            .ensureHistoryInitialized();

        var state = container.read(personalAssistantStreamControllerProvider);
        expect(historyLoader.loadCount, 1);
        expect(state.historyInitialized, isTrue);
        expect(state.transcript.map((item) => item.runtimeType), <Type>[
          UserTranscriptTimelineRow,
          AssistantAnswerTranscriptRow,
        ]);
        expect(
          (state.transcript.first as UserTranscriptTimelineRow).content,
          '旧问题：深圳天气',
        );
        expect(
          (state.transcript.last as AssistantAnswerTranscriptRow).content,
          '旧回答：深圳今天多云转晴。',
        );

        await container
            .read(personalAssistantStreamControllerProvider.notifier)
            .send('那明天呢');

        state = container.read(personalAssistantStreamControllerProvider);
        expect(historyLoader.loadCount, 1);
        expect(state.transcript.map((item) => item.runtimeType), <Type>[
          UserTranscriptTimelineRow,
          AssistantAnswerTranscriptRow,
          UserTranscriptTimelineRow,
          AssistantAnswerTranscriptRow,
        ]);
        expect(
          (state.transcript[2] as UserTranscriptTimelineRow).content,
          '那明天呢',
        );
        expect(
          (state.transcript[3] as AssistantAnswerTranscriptRow).content,
          '你好，我是找私助。',
        );
      },
    );

    test(
      'history load failure stays visible and retry restores the cloud transcript',
      () async {
        final repository = _FakeAssistantRepository(
          events: const <AssistantStreamEventWire>[],
        );
        final historyLoader = _FakeAssistantHistoryLoader(
          error: StateError('history storage unavailable'),
        );
        final container = _containerWith(
          assistantRepository: repository,
          historyLoader: historyLoader,
        );
        addTearDown(container.dispose);
        final controller = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );

        await controller.ensureHistoryInitialized();

        var state = container.read(personalAssistantStreamControllerProvider);
        expect(state.historyInitialized, isFalse);
        expect(state.historyLoading, isFalse);
        expect(state.retryAvailable, isTrue);
        expect(state.errorMessage, isNotEmpty);
        expect(state.transcript, isEmpty);

        await controller.send('不应在恢复失败后建立新会话');
        expect(repository.startedRunTexts, isEmpty);

        historyLoader
          ..error = null
          ..snapshot = await _buildAssistantHistorySnapshot();
        await controller.retryLastFailedAction();

        state = container.read(personalAssistantStreamControllerProvider);
        expect(historyLoader.loadCount, 3);
        expect(state.historyInitialized, isTrue);
        expect(state.retryAvailable, isFalse);
        expect(state.errorMessage, isEmpty);
        expect(state.transcript, hasLength(2));
      },
    );

    test(
      'keeps each personal assistant turn in canonical timeline order',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(
                seq: 1,
                eventType: 'process_replace',
                payload: const <String, dynamic>{'processes': <Object?>[]},
              ),
              _event(
                seq: 2,
                eventType: 'process_append',
                payload: const <String, dynamic>{
                  'process': <String, dynamic>{
                    'processId': 'planning',
                    'scope': 'root',
                    'stage': 'planning',
                    'status': 'completed',
                    'order': 1,
                    'summary': '我会查证公开信息后再回答。',
                  },
                },
              ),
              _event(
                seq: 3,
                eventType: 'process_commit',
                payload: const <String, dynamic>{
                  'process': <String, dynamic>{
                    'processId': 'assessing',
                    'scope': 'aggregation',
                    'stage': 'assessing',
                    'status': 'completed',
                    'order': 2,
                    'summary': '已整理检索要点。',
                  },
                },
              ),
              _event(
                seq: 4,
                eventType: 'completed',
                payload: const <String, dynamic>{'text': '第一轮答案'},
              ),
            ],
          ),
        );
        addTearDown(container.dispose);

        final controller = container.read(
          personalAssistantStreamControllerProvider.notifier,
        );
        await controller.send('第一轮');
        await controller.send('第二轮');

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.transcript.map((item) => item.runtimeType), <Type>[
          UserTranscriptTimelineRow,
          AssistantAnswerTranscriptRow,
          UserTranscriptTimelineRow,
          AssistantAnswerTranscriptRow,
        ]);
        final firstAssistant =
            state.transcript[1] as AssistantAnswerTranscriptRow;
        final secondAssistant =
            state.transcript[3] as AssistantAnswerTranscriptRow;
        expect(
          firstAssistant.persisted.toMap()[assistantProcessTimelineField],
          isNotEmpty,
        );
        expect(
          secondAssistant.persisted.toMap()[assistantProcessTimelineField],
          isNotEmpty,
        );
        expect(firstAssistant.id, isNot(secondAssistant.id));
      },
    );

    test(
      'terminal replay restores process and citation from completed snapshot',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(
                seq: 9,
                eventType: 'completed',
                payload: const <String, dynamic>{
                  'finalAnswer': 'journal 过期后恢复的回答',
                  'processes': <Map<String, dynamic>>[
                    <String, dynamic>{
                      'processId': 'assessing',
                      'scope': 'aggregation',
                      'stage': 'assessing',
                      'status': 'completed',
                      'order': 2,
                      'summary': '已从终态快照恢复证据。',
                      'searchedDocumentCount': 2,
                      'processedDocumentCount': 2,
                      'acceptedDocumentCount': 1,
                      'acceptedReferences': <Map<String, dynamic>>[
                        <String, dynamic>{
                          'title': '终态引用',
                          'destination': <String, dynamic>{
                            'kind': 'external',
                            'url': 'https://example.com/terminal-reference',
                          },
                          'source': 'example.com',
                          'snippet': '终态公开摘要',
                        },
                      ],
                    },
                  ],
                },
              ),
            ],
          ),
        );
        addTearDown(container.dispose);

        await container
            .read(personalAssistantStreamControllerProvider.notifier)
            .send('恢复终态');

        final state = container.read(personalAssistantStreamControllerProvider);
        expect(state.answer, 'journal 过期后恢复的回答');
        expect(state.processSummary.processes, hasLength(1));
        expect(state.processSummary.acceptedCount, 1);
        expect(
          state.processSummary.acceptedReferences.single.destination.url,
          'https://example.com/terminal-reference',
        );
      },
    );

    test('projects runtime failure instead of raw debug text', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'failed',
              runtimeFailure: const RuntimeFailureWire(
                code: 'ASSISTANT.MIDDLEWARE.tool_failed',
              ),
            ),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('搜索新闻');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.answer, isEmpty);
      expect(state.errorMessage, AssistantErrorCode.unknown.defaultMessage);
      expect(
        state.events.single.runtimeFailure?.code,
        contains('ASSISTANT.MIDDLEWARE.tool_failed'),
      );
      expect(
        (state.transcript.last as AssistantAnswerTranscriptRow).content,
        AssistantErrorCode.unknown.defaultMessage,
      );
    });

    test(
      'uses retrievalProcessing counts instead of tool event counts',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(seq: 1, eventType: 'run_started'),
              _event(
                seq: 2,
                eventType: 'process_append',
                payload: const <String, dynamic>{
                  'process': <String, dynamic>{
                    'processId': 'searching',
                    'scope': 'skill',
                    'stage': 'searching',
                    'status': 'completed',
                    'order': 1,
                    'toolName': 'web_search',
                  },
                },
              ),
              _event(
                seq: 3,
                eventType: 'process_commit',
                payload: const <String, dynamic>{
                  'process': <String, dynamic>{
                    'processId': 'assessing',
                    'scope': 'aggregation',
                    'stage': 'assessing',
                    'status': 'completed',
                    'order': 2,
                    'searchedDocumentCount': 3,
                    'processedDocumentCount': 3,
                    'acceptedDocumentCount': 1,
                    'summary': '接纳 1 条核心天气证据。',
                    'acceptedReferences': <Map<String, dynamic>>[
                      <String, dynamic>{
                        'title': 'Open-Meteo Forecast API - 深圳，广东',
                        'destination': <String, dynamic>{
                          'kind': 'external',
                          'url': 'https://open-meteo.com/en/docs',
                        },
                        'source': 'open_meteo_forecast',
                      },
                    ],
                  },
                },
              ),
              _event(
                seq: 4,
                eventType: 'completed',
                payload: const <String, dynamic>{'text': '深圳天气回答'},
              ),
            ],
          ),
        );
        addTearDown(container.dispose);

        await container
            .read(personalAssistantStreamControllerProvider.notifier)
            .send('深圳天气');

        final summary = container
            .read(personalAssistantStreamControllerProvider)
            .processSummary;
        expect(summary.searchCount, 3);
        expect(summary.processedCount, 3);
        expect(summary.acceptedCount, 1);
        expect(
          summary.acceptedReferences.single.destination.url,
          'https://open-meteo.com/en/docs',
        );
      },
    );

    test('在回答生成过程提交后持久化回答组织叙述', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'process_commit',
              payload: const <String, dynamic>{
                'process': <String, dynamic>{
                  'processId': 'assessing',
                  'scope': 'aggregation',
                  'stage': 'assessing',
                  'status': 'completed',
                  'order': 1,
                  'searchedDocumentCount': 3,
                  'processedDocumentCount': 3,
                  'acceptedDocumentCount': 2,
                  'summary': '已核对深圳天气权威来源。',
                },
              },
            ),
            _event(
              seq: 3,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '深圳今天适合'},
            ),
            _event(
              seq: 4,
              eventType: 'process_commit',
              payload: const <String, dynamic>{
                'process': <String, dynamic>{
                  'processId': 'answering',
                  'scope': 'root',
                  'stage': 'answering',
                  'status': 'completed',
                  'order': 2,
                },
              },
            ),
            _event(
              seq: 5,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '深圳今天适合短时户外活动，请留意午后阵雨。'},
            ),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('Shen zhen tian qi');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.answer, contains('深圳今天适合短时户外活动'));
      expect(state.processSummary.finalAnswerReady, isTrue);
      expect(state.processSummary.finalAnswerSummary, '已结合检索与核对结果生成最终回答。');

      final assistantRow =
          state.transcript.last as AssistantAnswerTranscriptRow;
      final processTimeline =
          assistantRow.persisted.toMap()[assistantProcessTimelineField]
              as List<dynamic>;
      expect(
        processTimeline.cast<Map>().any(
          (frame) =>
              frame['stepId'] == 'answer_organization' &&
              frame['headline'] == '已结合检索与核对结果生成最终回答。',
        ),
        isTrue,
      );
    });

    test(
      'projects user-visible planning summary without raw search queries',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(seq: 1, eventType: 'run_started'),
              _event(
                seq: 2,
                eventType: 'process_append',
                payload: const <String, dynamic>{
                  'process': <String, dynamic>{
                    'processId': 'planning',
                    'scope': 'root',
                    'stage': 'planning',
                    'status': 'completed',
                    'order': 1,
                    'summary': '你想确认深圳天气，并安排两天亲子外出；我会核对天气和活动条件。',
                  },
                },
              ),
              _event(
                seq: 3,
                eventType: 'completed',
                payload: const <String, dynamic>{'text': '深圳亲子出行建议'},
              ),
            ],
          ),
        );
        addTearDown(container.dispose);

        await container
            .read(personalAssistantStreamControllerProvider.notifier)
            .send('深圳天气和亲子出行');

        final summary = container
            .read(personalAssistantStreamControllerProvider)
            .processSummary;
        expect(summary.understandingSummary, contains('你想确认深圳天气'));
        expect(summary.retrievalDesignNarrative, contains('核对天气和活动条件'));
      },
    );

    test('loads app message unread summary', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        ),
        appMessageQuery: _FakeAppMessageQuery(unreadCount: 2),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .refreshManagementSummary();

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.appMessageUnreadCount, 2);
      expect(state.managementSummaryLoading, isFalse);
    });

    test('opens app message target turn in personal assistant state', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .openRunFromAppMessage('arn_test_personal');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.runId, 'arn_test_personal');
      expect(state.sessionId, 'asn_mock_personal_assistant');
      expect(state.answer, contains('已打开主动提醒'));
      expect(
        state.transcript.map(
          (item) =>
              item is AssistantAnswerTranscriptRow &&
              item.extra['proactive'] == true,
        ),
        <bool>[true, true],
      );
      expect(state.transcript.last, isA<AssistantAnswerTranscriptRow>());
    });

    test(
      'skill center separates default enablement from proactive subscription',
      () async {
        final repository = _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        );
        final container = _containerWith(assistantRepository: repository);
        addTearDown(container.dispose);

        var items = await container.read(assistantSkillCenterProvider.future);
        expect(items.any((item) => item.skillId == 'stock_sentinel'), isTrue);
        expect(
          items
              .where((item) => item.skillId == 'stock_sentinel')
              .single
              .enabled,
          isTrue,
        );
        expect(
          items
              .where((item) => item.skillId == 'stock_sentinel')
              .single
              .subscriptions,
          isEmpty,
        );

        await repository.createSkillSubscription(
          skillId: 'stock_sentinel',
          domainId: 'finance',
          rawText: '每天开盘前提醒我关注的股票重大消息',
          clientRequestId: 'create-stock-sentinel',
        );
        container.invalidate(assistantSkillCenterProvider);
        items = await container.read(assistantSkillCenterProvider.future);

        final stock = items
            .where((item) => item.skillId == 'stock_sentinel')
            .single;
        expect(stock.enabled, isTrue);
        expect(stock.subscriptions, hasLength(1));
        expect(
          stock.subscriptions.single.status,
          SkillSubscriptionStatus.active,
        );
      },
    );

    test('无 runId 时反馈仅本地记录，不产生学习上报', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .submitFeedback('too_frequent');
      await pumpEventQueue();

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.feedbackMessage, contains('太频繁'));
      expect(repository.learningFacts, isEmpty);
    });

    // ── C. 学习回路：submitFeedback → AppendAssistantLearningFact ──
    test('submitFeedback 追加学习事实且 eventId 稳定派生', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '反馈用回答'},
          ),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await controller.send('反馈用问题');
      await controller.submitFeedback('useful');
      await pumpEventQueue();

      expect(repository.learningFacts, hasLength(1));
      final fact = repository.learningFacts.single;
      expect(fact.eventId, 'fb:arn_test_personal:useful');
      expect(fact.assistantTurnId, 'arn_test_personal');
      expect(fact.factType, AssistantLearningFactType.userFeedback.wireName);
      expect(
        fact.referralSource,
        AssistantReferralSource.assistantSession.wireName,
      );
      expect(fact.domainId, 'assistant');
      expect(fact.feedbackType, FeedbackType.useful.wireName);
      expect(fact.trainingEligible, isFalse);
      expect(controller.pendingFeedbackEventCount, 0);

      // 同一反馈重复点击是本地 no-op，不生成同 identity、不同 occurredAt 的冲突事实。
      await controller.submitFeedback('useful');
      await pumpEventQueue();
      expect(repository.learningFacts, hasLength(1));

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(
        state.feedbackMessage,
        contains(AssistantText.assistantFeedbackUsefulLabel),
      );
      expect(state.feedbackType, 'useful');
    });

    test('学习上报失败不阻塞 UI，事件进待重试并在下一轮 turn 完成后补发', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '第一轮回答'},
          ),
        ],
      );
      repository.failLearningFactAppend = true;
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await controller.send('第一轮');
      await controller.submitFeedback('irrelevant');
      await pumpEventQueue();

      // UI 展示不被上报失败阻塞；事件保留在加密持久待重试队列。
      var state = container.read(personalAssistantStreamControllerProvider);
      expect(
        state.feedbackMessage,
        contains(AssistantText.assistantFeedbackIrrelevantLabel),
      );
      expect(state.feedbackType, 'irrelevant');
      expect(controller.pendingFeedbackEventCount, 1);

      repository.failLearningFactAppend = false;
      await controller.send('第二轮');
      await pumpEventQueue();

      expect(controller.pendingFeedbackEventCount, 0);
      expect(
        repository.learningFacts.map((fact) => fact.eventId),
        contains('fb:arn_test_personal:irrelevant'),
      );
      state = container.read(personalAssistantStreamControllerProvider);
      expect(state.feedbackMessage, isEmpty);
      expect(state.feedbackType, isEmpty);
    });

    test('学习部分确认只移除已确认的稳定反馈事件', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '第一轮回答'},
          ),
        ],
      )..failLearningFactAppend = true;
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await controller.send('第一轮');
      await controller.submitFeedback('useful');
      await controller.submitFeedback('irrelevant');
      await pumpEventQueue();
      expect(controller.pendingFeedbackEventCount, 2);

      repository
        ..failLearningFactAppend = false
        ..rejectedLearningFactIds.add('fb:arn_test_personal:irrelevant');
      await controller.send('第二轮');
      await _flushLearningFactOutbox(container);
      await pumpEventQueue();

      expect(controller.pendingFeedbackEventCount, 1);
      expect(
        repository.learningFacts.map((fact) => fact.eventId),
        containsAll(<String>[
          'fb:arn_test_personal:useful',
          'fb:arn_test_personal:irrelevant',
        ]),
      );

      repository.rejectedLearningFactIds.clear();
      await controller.send('第三轮');
      await _flushLearningFactOutbox(container);
      await pumpEventQueue();

      expect(controller.pendingFeedbackEventCount, 0);
      expect(
        repository.learningFacts.last.eventId,
        'fb:arn_test_personal:irrelevant',
      );
    });

    // ── P3 飞轮小循环：turn.completed emergedTags → assistant_interest 回流 ──
    test('completed 的 emergedTags 合成 assistant_interest 行为回流', () async {
      final behaviorRepo = RecordingContentBehaviorRepository();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '稻城亚丁秋季最佳。'},
            ),
            _event(
              seq: 3,
              eventType: 'completed',
              payload: const <String, dynamic>{
                'status': 'completed',
                'finalAnswer': '稻城亚丁秋季最佳。',
                'emergedTags': <String>['Topic/旅行', 'Topic/景区', 'Topic/旅行'],
              },
            ),
          ],
        ),
        behaviorRepository: behaviorRepo,
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('稻城亚丁什么时候去最好');
      await container.read(contentBehaviorTrackerProvider).flush();

      final interest = behaviorRepo.recorded
          .where((e) => e.action == BehaviorEventType.assistantInterest)
          .toList();
      expect(interest, hasLength(1));
      expect(interest.single.tags, equals(<String>['Topic/旅行', 'Topic/景区']));
      expect(interest.single.contentId, isEmpty);
    });

    test('无 completed emergedTags 时不回流 assistant_interest', () async {
      final behaviorRepo = RecordingContentBehaviorRepository();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'completed',
              payload: const <String, dynamic>{'text': '没有命中站内内容。'},
            ),
          ],
        ),
        behaviorRepository: behaviorRepo,
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('一个不触发站内检索的问题');
      await container.read(contentBehaviorTrackerProvider).flush();

      expect(behaviorRepo.recorded, isEmpty);
    });

    test('extractAssistantEmergedTags 仅取 completed 并去重过滤空值', () {
      final tags = extractAssistantEmergedTags(<AssistantStreamEventWire>[
        _event(
          seq: 1,
          eventType: 'answer_delta',
          payload: const <String, dynamic>{
            'emergedTags': <String>['Topic/应忽略'],
          },
        ),
        _event(
          seq: 2,
          eventType: 'completed',
          payload: const <String, dynamic>{
            'emergedTags': <String>['Topic/旅行', ' Topic/景区 ', 'Topic/旅行', ''],
          },
        ),
      ]);
      expect(tags, equals(<String>['Topic/旅行', 'Topic/景区']));
    });

    // ---- 会话生命周期新能力合同（R-ASSIST-001 收口）----

    test('缺少终态事件的中断流进入可重试失败而非伪造完成', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(seq: 1, eventType: 'run_started'),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await notifier.send('长问题');
      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.running, isFalse);
      expect(state.errorMessage, isNotEmpty);
      expect(state.retryAvailable, isTrue);
      // 失败收尾后没有可取消的运行中任务。
      await notifier.stopGeneration();
      expect(repository.cancelledRunIds, isEmpty);
    });

    test('cancelled 且无回答增量时收尾为停止占位', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'cancelled',
              payload: const <String, dynamic>{'status': 'cancelled'},
            ),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('被取消的问题');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.running, isFalse);
      expect(state.errorMessage, isEmpty);
      final assistantRow =
          state.transcript.last as AssistantAnswerTranscriptRow;
      expect(assistantRow.content, AssistantText.assistantGenerationStopped);
      expect(assistantRow.streaming, isFalse);
    });

    test('cancelled 保留已生成的回答增量', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'run_started'),
            _event(
              seq: 2,
              eventType: 'answer_delta',
              payload: const <String, dynamic>{'text': '已生成一半'},
            ),
            _event(
              seq: 3,
              eventType: 'cancelled',
              payload: const <String, dynamic>{'status': 'cancelled'},
            ),
          ],
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send('被中途取消的问题');

      final state = container.read(personalAssistantStreamControllerProvider);
      final assistantRow =
          state.transcript.last as AssistantAnswerTranscriptRow;
      expect(assistantRow.content, '已生成一半');
      expect(assistantRow.streaming, isFalse);
    });

    test('switchSession 经 loader 恢复指定会话并绑定 sessionId', () async {
      final historyLoader = _SwitchRecordingHistoryLoader(
        snapshot: await _buildAssistantHistorySnapshot(),
      );
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: const <AssistantStreamEventWire>[],
        ),
        historyLoader: historyLoader,
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await notifier.switchSession('asn_target_001');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(historyLoader.requestedSessionIds, <String>['asn_target_001']);
      expect(state.sessionId, 'asn_target_001');
      expect(state.historyInitialized, isTrue);
      expect(state.historyLoading, isFalse);
      expect(state.transcript, isNotEmpty);
    });

    test('startNewSession 清空会话状态供下次 send 新建云端会话', () async {
      final historyLoader = _FakeAssistantHistoryLoader(
        snapshot: await _buildAssistantHistorySnapshot(),
      );
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: const <AssistantStreamEventWire>[],
        ),
        historyLoader: historyLoader,
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await notifier.ensureHistoryInitialized();
      expect(
        container.read(personalAssistantStreamControllerProvider).sessionId,
        'restored_session_001',
      );

      notifier.startNewSession();

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.sessionId, isEmpty);
      expect(state.runId, isEmpty);
      expect(state.transcript, isEmpty);
      expect(state.historyInitialized, isTrue);
    });

    test('ensureHistoryInitialized 绑定最近云端会话 sessionId 供续聊', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: const <AssistantStreamEventWire>[],
        ),
        historyLoader: _FakeAssistantHistoryLoader(
          snapshot: await _buildAssistantHistorySnapshot(),
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .ensureHistoryInitialized();

      expect(
        container.read(personalAssistantStreamControllerProvider).sessionId,
        'restored_session_001',
      );
    });

    test('regenerateLastAnswer 保持原问题并先写入会话偏好', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '第一次回答'},
          ),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await notifier.send('原始问题');
      await notifier.regenerateLastAnswer();
      await notifier.regenerateLastAnswer(option: RegenerateOption.concise);
      await _flushLearningFactOutbox(container);

      expect(repository.startedRunTexts, <String>['原始问题', '原始问题', '原始问题']);
      final preferences = await repository.listAssistantPreferences(
        scope: AssistantPreferenceScope.session,
      );
      expect(preferences, hasLength(1));
      expect(preferences.single.kind, AssistantPreferenceKind.replyLength);
      expect(preferences.single.value, 'concise');
      // 学习信号：regenerate 以 interaction_outcome 事实追加。
      final regenerated = repository.learningFacts
          .where(
            (fact) =>
                fact.factType ==
                    AssistantLearningFactType.interactionOutcome.wireName &&
                fact.feedbackType == FeedbackType.regenerated.wireName,
          )
          .toList();
      expect(regenerated, isNotEmpty);
    });

    test('ApproveTool 批准与 Device receipt 保持两个独立 command', () async {
      final repository = _FakeAssistantRepository(
        events: const <AssistantStreamEventWire>[],
        approvalDevicePermit: _devicePermit(),
      );
      final executor = _RecordingAssistantDeviceActionExecutor();
      final container = _containerWith(
        assistantRepository: repository,
        deviceActionExecutor: executor,
        deviceBinding: const DeviceCalendarLocalBinding(
          installationId: 'installation_test',
          deviceId: 'device_test',
        ),
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      final approved = _approveToolAction();

      expect(notifier.canHandlePresentationAction(approved), isTrue);
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: approved,
      );

      expect(repository.approvedToolUses, hasLength(1));
      expect(repository.approvedToolUses.single.decision, 'approved');
      expect(executor.intents, hasLength(1));
      expect(repository.deviceReceipts, hasLength(1));
      expect(repository.deviceReceipts.single.receipt.outcome, 'completed');
      expect(
        repository.deviceReceipts.single.receipt.deviceObjectId,
        'calendar_event_1',
      );

      final rejected = _approveToolAction(
        decision: 'rejected',
        intentId: 'reject_calendar',
        jti: 'reject_calendar_jti',
      );
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: rejected,
      );
      expect(repository.approvedToolUses, hasLength(2));
      expect(repository.approvedToolUses.last.decision, 'rejected');
      expect(executor.intents, hasLength(1));
      expect(repository.deviceReceipts, hasLength(1));
    });

    test('批准结果没有 Device permit 时不等于设备执行成功', () async {
      final repository = _FakeAssistantRepository(
        events: const <AssistantStreamEventWire>[],
      );
      final executor = _RecordingAssistantDeviceActionExecutor();
      final container = _containerWith(
        assistantRepository: repository,
        deviceActionExecutor: executor,
        deviceBinding: const DeviceCalendarLocalBinding(
          installationId: 'installation_test',
          deviceId: 'device_test',
        ),
      );
      addTearDown(container.dispose);

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .handlePresentationAction(
            runId: 'arn_action',
            action: _approveToolAction(),
          );

      expect(repository.approvedToolUses, hasLength(1));
      expect(executor.intents, isEmpty);
      expect(repository.deviceReceipts, isEmpty);
    });

    test('未知 kind、过期、digest mismatch 与 replay 均零新增执行', () async {
      final repository = _FakeAssistantRepository(
        events: const <AssistantStreamEventWire>[],
      );
      final executor = _RecordingAssistantDeviceActionExecutor();
      final container = _containerWith(
        assistantRepository: repository,
        deviceActionExecutor: executor,
        deviceBinding: const DeviceCalendarLocalBinding(
          installationId: 'installation_test',
          deviceId: 'device_test',
        ),
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      final invalid = <AssistantActionIntentWire>[
        _navigateAction(kind: 'Unknown'),
        _approveToolAction(expired: true),
        _approveToolAction(
          intentId: 'digest_mismatch',
          jti: 'digest_mismatch_jti',
          requestDigest:
              'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
        ),
      ];
      for (final action in invalid) {
        expect(notifier.canHandlePresentationAction(action), isFalse);
        await notifier.handlePresentationAction(
          runId: 'arn_action',
          action: action,
        );
      }
      expect(repository.approvedToolUses, isEmpty);
      expect(executor.intents, isEmpty);
      expect(repository.deviceReceipts, isEmpty);

      final mismatchedDevice = _executeDeviceAction(
        intentId: 'execute_wrong_device',
        jti: 'execute_wrong_device_jti',
        idempotencyKey: 'execute_wrong_device_once',
        deviceId: 'device_other',
      );
      expect(notifier.canHandlePresentationAction(mismatchedDevice), isFalse);
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: mismatchedDevice,
      );
      expect(executor.intents, isEmpty);
      expect(repository.deviceReceipts, isEmpty);

      final execute = _executeDeviceAction();
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: execute,
      );
      expect(notifier.canHandlePresentationAction(execute), isFalse);
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: execute,
      );
      expect(executor.intents, hasLength(1));
      expect(repository.deviceReceipts, hasLength(1));
    });

    test('Navigate 与 ProvideInput 分别进入强类型 handler', () async {
      final navigate = _RecordingNavigateIntentHandler();
      final input = _RecordingProvideInputIntentHandler();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: const <AssistantStreamEventWire>[],
        ),
        navigateIntentHandler: navigate,
        provideInputIntentHandler: input,
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      final navigateAction = _navigateAction();
      final inputAction = _provideInputAction();
      expect(notifier.canHandlePresentationAction(navigateAction), isTrue);
      expect(notifier.canHandlePresentationAction(inputAction), isTrue);
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: navigateAction,
      );
      await notifier.handlePresentationAction(
        runId: 'arn_action',
        action: inputAction,
      );

      expect(navigate.intents.single.routeId, 'post_detail');
      expect(input.intents.single.inputName, 'confirmation');
    });
  });
}

/// 记录 switchSession 请求的 loader 桩。
class _SwitchRecordingHistoryLoader implements AssistantHistoryLoader {
  _SwitchRecordingHistoryLoader({this.snapshot});

  final AssistantHistorySnapshot? snapshot;
  final List<String> requestedSessionIds = <String>[];

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async {
    if (sessionId.isNotEmpty) {
      requestedSessionIds.add(sessionId);
    }
    return snapshot;
  }
}

const _inputDigest =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

AssistantDeviceActionPermit _devicePermit() => AssistantDeviceActionPermit(
  runId: 'arn_action',
  toolInvocationId: 'tool_calendar',
  installationId: 'installation_test',
  deviceId: 'device_test',
  capability: 'calendar_create_reminder',
  inputDigest: _inputDigest,
  idempotencyKey: 'device_action_once',
  approvalRef: 'approval_calendar',
  expiresAt: DateTime.now()
      .toUtc()
      .add(const Duration(minutes: 2))
      .toIso8601String(),
  permit: 'opaque_device_action_permit_0123456789',
);

AssistantActionIntentWire _approveToolAction({
  String decision = 'approved',
  String intentId = 'approve_calendar',
  String jti = 'approve_calendar_jti',
  String? requestDigest,
  bool expired = false,
}) {
  final now = DateTime.now().toUtc();
  final contract = AssistantApproveToolIntentWire(
    runId: 'arn_action',
    toolInvocationId: 'tool_calendar',
    decision: decision,
    capability: 'calendar_create_reminder',
    inputDigest: _inputDigest,
    approvalPermit: 'opaque_approval_permit_0123456789',
  );
  return AssistantActionIntentWire(
    intentId: intentId,
    kind: 'ApproveTool',
    requestDigest:
        requestDigest ?? assistantActionIntentRequestDigest(contract.toJson()),
    jti: jti,
    issuedAt:
        (expired
                ? now.subtract(const Duration(minutes: 3))
                : now.subtract(const Duration(seconds: 1)))
            .toIso8601String(),
    expiresAt:
        (expired
                ? now.subtract(const Duration(seconds: 1))
                : now.add(const Duration(minutes: 2)))
            .toIso8601String(),
    approveTool: contract,
  );
}

AssistantActionIntentWire _executeDeviceAction({
  String intentId = 'execute_calendar',
  String jti = 'execute_calendar_jti',
  String idempotencyKey = 'execute_action_once',
  String deviceId = 'device_test',
}) {
  final now = DateTime.now().toUtc();
  final contract = AssistantExecuteDeviceActionIntentWire(
    runId: 'arn_action',
    toolInvocationId: 'tool_calendar',
    installationId: 'installation_test',
    deviceId: deviceId,
    capability: 'calendar_create_reminder',
    inputDigest: _inputDigest,
    idempotencyKey: idempotencyKey,
    deviceActionPermit: 'opaque_device_action_permit_0123456789',
  );
  return AssistantActionIntentWire(
    intentId: intentId,
    kind: 'ExecuteDeviceAction',
    requestDigest: assistantActionIntentRequestDigest(contract.toJson()),
    jti: jti,
    issuedAt: now.subtract(const Duration(seconds: 1)).toIso8601String(),
    expiresAt: now.add(const Duration(minutes: 2)).toIso8601String(),
    executeDeviceAction: contract,
  );
}

AssistantActionIntentWire _navigateAction({String kind = 'Navigate'}) {
  final now = DateTime.now().toUtc();
  const contract = AssistantNavigateIntentWire(
    routeId: 'post_detail',
    objectTypeRef: 'content_post',
    objectId: 'post_1',
  );
  return AssistantActionIntentWire(
    intentId: 'navigate_post',
    kind: kind,
    requestDigest: assistantActionIntentRequestDigest(contract.toJson()),
    jti: 'navigate_post_jti',
    issuedAt: now.subtract(const Duration(seconds: 1)).toIso8601String(),
    expiresAt: now.add(const Duration(minutes: 2)).toIso8601String(),
    navigate: contract,
  );
}

AssistantActionIntentWire _provideInputAction() {
  final now = DateTime.now().toUtc();
  const contract = AssistantProvideInputIntentWire(
    runId: 'arn_action',
    toolInvocationId: 'tool_input',
    inputName: 'confirmation',
    inputSchemaRef: 'assistant_confirmation',
    inputPermit: 'opaque_input_permit_0123456789',
  );
  return AssistantActionIntentWire(
    intentId: 'provide_confirmation',
    kind: 'ProvideInput',
    requestDigest: assistantActionIntentRequestDigest(contract.toJson()),
    jti: 'provide_confirmation_jti',
    issuedAt: now.subtract(const Duration(seconds: 1)).toIso8601String(),
    expiresAt: now.add(const Duration(minutes: 2)).toIso8601String(),
    provideInput: contract,
  );
}

class _RecordingAssistantDeviceActionExecutor
    implements AssistantDeviceActionExecutor {
  _RecordingAssistantDeviceActionExecutor({
    AssistantDeviceActionExecutionResult? result,
  }) : result =
           result ??
           AssistantDeviceActionExecutionResult(
             outcome: 'completed',
             executedAt: DateTime.utc(2026, 8, 6, 9),
             deviceObjectId: 'calendar_event_1',
           );

  final AssistantDeviceActionExecutionResult result;
  final List<AssistantExecuteDeviceActionIntentWire> intents =
      <AssistantExecuteDeviceActionIntentWire>[];

  @override
  bool canExecute(AssistantExecuteDeviceActionIntentWire intent) => true;

  @override
  Future<AssistantDeviceActionExecutionResult> execute(
    AssistantExecuteDeviceActionIntentWire intent,
  ) async {
    intents.add(intent);
    return result;
  }
}

class _RecordingNavigateIntentHandler
    implements AssistantNavigateIntentHandler {
  final List<AssistantNavigateIntentWire> intents =
      <AssistantNavigateIntentWire>[];

  @override
  bool canNavigate(AssistantNavigateIntentWire intent) => true;

  @override
  Future<void> navigate(AssistantNavigateIntentWire intent) async {
    intents.add(intent);
  }
}

class _RecordingProvideInputIntentHandler
    implements AssistantProvideInputIntentHandler {
  final List<AssistantProvideInputIntentWire> intents =
      <AssistantProvideInputIntentWire>[];

  @override
  bool canProvideInput(AssistantProvideInputIntentWire intent) => true;

  @override
  Future<void> provideInput(AssistantProvideInputIntentWire intent) async {
    intents.add(intent);
  }
}

ProviderContainer _containerWith({
  required InMemoryAssistantFacets assistantRepository,
  AppMessageQuery? appMessageQuery,
  AssistantHistoryLoader? historyLoader,
  BehaviorRepository? behaviorRepository,
  RecordingAppTelemetryRecorder? telemetryRecorder,
  AssistantDeviceActionExecutor? deviceActionExecutor,
  AssistantNavigateIntentHandler? navigateIntentHandler,
  AssistantProvideInputIntentHandler? provideInputIntentHandler,
  DeviceCalendarLocalBinding? deviceBinding,
}) {
  return ProviderContainer(
    overrides: [
      ...assistantFacetOverrides(assistantRepository),
      actorQueueStorageProvider.overrideWithValue(_actorQueueStorage),
      assistantLearningFactOutboxEnvironmentProvider.overrideWithValue('alpha'),
      currentUserIdProvider.overrideWithValue('persona_test'),
      resolvedOwnerUserIdProvider.overrideWithValue('user_test'),
      if (deviceActionExecutor != null)
        assistantDeviceActionExecutorProvider.overrideWithValue(
          deviceActionExecutor,
        ),
      if (navigateIntentHandler != null)
        assistantNavigateIntentHandlerProvider.overrideWithValue(
          navigateIntentHandler,
        ),
      if (provideInputIntentHandler != null)
        assistantProvideInputIntentHandlerProvider.overrideWithValue(
          provideInputIntentHandler,
        ),
      if (deviceBinding != null)
        deviceCalendarLocalBindingProvider.overrideWithValue(deviceBinding),
      appMessageQueryProvider.overrideWithValue(
        appMessageQuery ?? _FakeAppMessageQuery(),
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
        historyLoader ?? const _EmptyAssistantHistoryLoader(),
      ),
      if (behaviorRepository != null)
        behaviorRepositoryProvider.overrideWithValue(behaviorRepository),
      if (telemetryRecorder != null)
        appTelemetryReporterProvider.overrideWithValue(telemetryRecorder),
    ],
  );
}

Future<void> _flushLearningFactOutbox(ProviderContainer container) =>
    container.read(assistantLearningFactOutboxProvider.notifier).flush();

Future<AssistantHistorySnapshot> _buildAssistantHistorySnapshot() async {
  // 云端历史恢复真相源：CloudAssistantHistoryLoader 消费 List sessions/turns
  // 查询面（与 api_integration 断言的服务端行为同源）。
  const sessionId = 'restored_session_001';
  final loader = CloudAssistantHistoryLoader(
    _HistoryFacetStub(
      session: AssistantSessionWire(
        sessionId: sessionId,
        userId: 'user_test',
        summary: '深圳天气',
        createdAt: '2026-07-20T10:00:00Z',
        updatedAt: '2026-07-20T10:05:00Z',
      ),
      turns: const <AssistantTurnSummaryView>[
        AssistantTurnSummaryView(
          turnId: 'turn_restored_001',
          sessionId: sessionId,
          status: 'completed',
          inputText: '旧问题：深圳天气',
          terminalSnapshot: AssistantRunTerminalSnapshotView(
            answerText: '旧回答：深圳今天多云转晴。',
            processes: [],
          ),
          createdAt: '2026-07-20T10:00:00Z',
          completedAt: '2026-07-20T10:00:30Z',
        ),
      ],
    ),
  );
  final snapshot = await loader.load(personaId: 'persona_test');
  return snapshot!;
}

/// 只服务历史恢复断言的最小 Facet 桩：List sessions/turns 返回预置数据，
/// 其余方法不应被 loader 触达。
class _HistoryFacetStub extends InMemoryAssistantFacets {
  _HistoryFacetStub({required this.session, required this.turns});

  final AssistantSessionWire session;
  final List<AssistantTurnSummaryView> turns;

  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) async {
    return AssistantSessionListView(items: <AssistantSessionWire>[session]);
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) async {
    return AssistantTurnListView(items: turns);
  }
}

AssistantStreamEventWire _event({
  required int seq,
  required String eventType,
  Map<String, dynamic> payload = const <String, dynamic>{},
  RuntimeFailureWire? runtimeFailure,
}) {
  final wirePayload = <String, dynamic>{...payload};
  if (eventType == 'completed' &&
      !wirePayload.containsKey('finalAnswer') &&
      wirePayload['text'] is String) {
    wirePayload['finalAnswer'] = wirePayload['text'];
  }
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
    eventId: 'evt_$seq',
    sessionId: 'asn_test_personal',
    runId: 'arn_test_personal',
    seq: seq,
    eventType: parseAssistantStreamEventTypeStrict(eventType),
    payload: wirePayload,
    runtimeFailure: runtimeFailure,
    createdAt: '2026-04-29T00:00:00Z',
  );
}

class _FakeAssistantRepository extends InMemoryAssistantFacets {
  _FakeAssistantRepository({required this.events, this.approvalDevicePermit});

  final List<AssistantStreamEventWire> events;
  final AssistantDeviceActionPermit? approvalDevicePermit;
  int _turnCounter = 0;
  int createSessionFailuresRemaining = 0;
  int startRunFailuresRemaining = 0;
  bool failPageContextReport = false;
  final List<String> createdSessionRequestIds = <String>[];
  final List<String> startedRunClientRequestIds = <String>[];
  final List<String> callOrder = <String>[];
  final List<String> reportedPageContextActions = <String>[];
  AssistantOpenContext? reportedPageContext;

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    callOrder.add('reportPageContext');
    reportedPageContext = context;
    reportedPageContextActions.add(userAction ?? '');
    if (failPageContextReport) {
      throw StateError('page context unavailable (test)');
    }
    return PageContextReceipt(
      accepted: true,
      contextKey: 'ctx_test',
      expiresAt: '2026-08-02T12:05:00Z',
    );
  }

  /// 记录单轨学习事实 command；可按 eventId 模拟失败以覆盖重试语义。
  final List<AssistantLearningFactAppendCommand> learningFacts =
      <AssistantLearningFactAppendCommand>[];
  bool failLearningFactAppend = false;
  final Set<String> rejectedLearningFactIds = <String>{};

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    learningFacts.add(request);
    if (failLearningFactAppend ||
        rejectedLearningFactIds.contains(request.eventId)) {
      throw StateError('learning append unavailable (test)');
    }
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: learningFacts.length,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    createdSessionRequestIds.add(clientRequestId);
    if (createSessionFailuresRemaining > 0) {
      createSessionFailuresRemaining -= 1;
      throw StateError('assistant session unavailable (test)');
    }
    return const AssistantSessionWire(
      sessionId: 'asn_test_personal',
      userId: 'user_test',
      createdAt: '2026-04-29T00:00:00Z',
      updatedAt: '2026-04-29T00:00:00Z',
    );
  }

  /// 记录 StartAssistantRun 提交文本（regenerate 合同断言消费）。
  final List<String> startedRunTexts = <String>[];
  List<AssistantIntersectionEvidenceRef> startedIntersectionEvidenceRefs =
      const <AssistantIntersectionEvidenceRef>[];

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    callOrder.add('startAssistantRun');
    _turnCounter += 1;
    startedRunTexts.add(text);
    startedRunClientRequestIds.add(clientRequestId);
    startedIntersectionEvidenceRefs =
        List<AssistantIntersectionEvidenceRef>.unmodifiable(
          intersectionEvidenceRefs,
        );
    if (startRunFailuresRemaining > 0) {
      startRunFailuresRemaining -= 1;
      throw StateError('assistant start unavailable (test)');
    }
    return AssistantRunEnvelopeWire(
      runId: _turnCounter == 1
          ? 'arn_test_personal'
          : 'arn_test_personal_$_turnCounter',
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  /// 记录 CancelAssistantRun 调用（stopGeneration 合同断言消费）。
  final List<String> cancelledRunIds = <String>[];
  final List<
    ({
      String runId,
      String toolInvocationId,
      String decision,
      String approvalPermit,
    })
  >
  approvedToolUses = [];
  final List<
    ({
      String runId,
      String toolInvocationId,
      AssistantDeviceActionExecutionReceipt receipt,
    })
  >
  deviceReceipts = [];

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) async {
    cancelledRunIds.add(runId);
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_test_personal',
      status: 'cancelled',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) async {
    approvedToolUses.add((
      runId: runId,
      toolInvocationId: toolInvocationId,
      decision: decision,
      approvalPermit: approvalPermit,
    ));
    return AssistantToolApprovalResult(
      runId: runId,
      state: decision == 'approved' ? 'executing' : 'cancelled',
      deviceActionPermit: decision == 'approved' ? approvalDevicePermit : null,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) async {
    deviceReceipts.add((
      runId: runId,
      toolInvocationId: toolInvocationId,
      receipt: receipt,
    ));
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_test_personal',
      status: 'executing',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    if (lastEventId.isNotEmpty && events.isEmpty) {
      yield _event(
        seq: (int.tryParse(lastEventId) ?? 0) + 1,
        eventType: 'completed',
        payload: <String, dynamic>{
          'status': 'completed',
          'finalAnswer': '设备上的系统日程已创建。',
        },
      );
      return;
    }
    yield* Stream<AssistantStreamEventWire>.fromIterable(events);
  }
}

class _FakeAppMessageQuery implements AppMessageQuery {
  _FakeAppMessageQuery({this.unreadCount = 0});

  final int unreadCount;

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    return AppMessage(
      messageId: query.messageId,
      userId: 'user_test',
      messageType: NotificationType.assistant,
      source: 'assistant_turn',
      sourceId: 'arn_test_personal',
      destination: const AppMessageDestination(type: 'user', id: 'user_test'),
      title: '找私助提醒',
      summary: '测试消息',
      target: const AppMessageTarget(
        targetType: 'assistant_turn',
        targetId: 'arn_test_personal',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 4, 29),
    );
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    return AppMessageUnreadCountSlice(unreadCount: unreadCount);
  }

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    return AppMessageInboxSlice(
      items: <AppMessage>[
        await getAppMessage(GetAppMessageQuery(messageId: 'msg_test_personal')),
      ],
    );
  }
}

class _FakeAssistantHistoryLoader implements AssistantHistoryLoader {
  _FakeAssistantHistoryLoader({this.snapshot, this.error});

  AssistantHistorySnapshot? snapshot;
  Object? error;
  int loadCount = 0;

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async {
    loadCount += 1;
    final failure = error;
    if (failure != null) {
      throw failure;
    }
    return snapshot;
  }
}

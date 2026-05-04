import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/app_message_dto.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/ui/assistant/providers/skill_subscription_controller.dart';
import '../../common/assistant/assistant_scenario_fixtures.dart';

void main() {
  group('PersonalAssistantStreamController', () {
    test('端侧 alpha 默认使用 mock repository 并投影 stub stream', () async {
      final scenarioPack = loadAssistantScenarioPack();
      final scenario = scenarioPack
          .assistantTurnScenariosFor('alpha')
          .firstWhere((item) => item.id == 'weather_trip_basic');
      final container = ProviderContainer(
        overrides: [
          assistantRepositoryProvider.overrideWithValue(
            ScenarioMockAssistantRepository(pack: scenarioPack),
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
      expect(CloudRuntimeConfig.isValidAppRuntimeEnv, isTrue);
      expect(
        container.read(appDataSourceModeProvider),
        expectedRepositoryModeForCurrentRuntimeEnv(scenarioPack),
      );
      expect(
        container.read(assistantRepositoryProvider),
        isA<MockAssistantRepository>(),
      );

      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question);

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.turnId, 'atn_fixture_${scenario.id}');
      expect(state.answer, scenario.alphaMockStream.finalAnswer);
      expect(state.transcript, hasLength(2));
      expect(state.transcript.first, isA<UserTranscriptTimelineRow>());
      expect(state.transcript.last, isA<AssistantAnswerTranscriptRow>());
      expect(state.errorMessage, isEmpty);
      expect(
        state.events.map((event) => event.eventType),
        containsAll(scenario.expectedEvents),
      );
    });

    test('projects typed stream and ignores duplicate seq', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'turn_started'),
            _event(
              seq: 2,
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '你好，'},
            ),
            _event(
              seq: 2,
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '重复'},
            ),
            _event(
              seq: 1,
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '乱序'},
            ),
            _event(
              seq: 3,
              eventType: 'final_answer',
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
      expect(state.conversationId, 'acv_test_personal');
      expect(state.turnId, 'atn_test_personal');
    });

    test(
      'keeps each personal assistant turn in canonical timeline order',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(
                seq: 1,
                eventType: 'plan_updated',
                payload: <String, dynamic>{
                  'understandingSnapshot': <String, dynamic>{
                    'userFacingSummary': '我会查证公开信息后再回答。',
                    'retrievalDesignNarrative': '围绕实时检索补充证据。',
                  },
                },
              ),
              _event(
                seq: 2,
                eventType: 'assistant.search_query.accepted',
                payload: const <String, dynamic>{
                  'userFacingNarrative': '我会查证公开信息后再回答。',
                  'acceptedSearchPlans': <Map<String, dynamic>>[
                    <String, dynamic>{'query': '天气', 'acceptReason': '需要实时信息'},
                  ],
                },
              ),
              _event(
                seq: 3,
                eventType: 'observation_assessed',
                payload: <String, dynamic>{
                  'retrievalProcessing': <String, dynamic>{
                    'processingSummary': '已整理检索要点。',
                    'selectedKeyPoints': <String>['要点'],
                  },
                },
              ),
              _event(
                seq: 4,
                eventType: 'final_answer',
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
        expect(firstAssistant.runArtifacts['processTimeline'], isNotEmpty);
        expect(secondAssistant.runArtifacts['processTimeline'], isNotEmpty);
        expect(firstAssistant.id, isNot(secondAssistant.id));
      },
    );

    test('projects runtime failure instead of raw debug text', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'turn_failed',
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
      expect(state.errorMessage, contains('找私助执行遇到问题'));
      expect(
        state.events.single.runtimeFailure?.code,
        contains('ASSISTANT.MIDDLEWARE.tool_failed'),
      );
      expect(
        (state.transcript.last as AssistantAnswerTranscriptRow).content,
        contains('找私助执行遇到问题'),
      );
    });

    test(
      'uses retrievalProcessing counts instead of tool event counts',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(seq: 1, eventType: 'turn_started'),
              _event(
                seq: 2,
                eventType: 'tool_use_requested',
                payload: const <String, dynamic>{
                  'toolUse': <String, dynamic>{'toolName': 'web_search'},
                },
              ),
              _event(
                seq: 3,
                eventType: 'tool_result_received',
                payload: const <String, dynamic>{
                  'toolUse': <String, dynamic>{'toolName': 'web_search'},
                },
              ),
              _event(
                seq: 4,
                eventType: 'observation_assessed',
                payload: const <String, dynamic>{
                  'retrievalProcessing': <String, dynamic>{
                    'searchedDocumentCount': 3,
                    'processedDocumentCount': 3,
                    'acceptedDocumentCount': 1,
                    'processingSummary': '接纳 1 条核心天气证据。',
                    'acceptedReferences': <Map<String, dynamic>>[
                      <String, dynamic>{
                        'title': 'Open-Meteo Forecast API - 深圳，广东',
                        'url': 'https://open-meteo.com/en/docs',
                        'source': 'open_meteo_forecast',
                      },
                    ],
                  },
                },
              ),
              _event(
                seq: 5,
                eventType: 'final_answer',
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
          summary.acceptedReferences.single.url,
          'https://open-meteo.com/en/docs',
        );
      },
    );

    test('persists answer organization narrative after final answer', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'turn_started'),
            _event(
              seq: 2,
              eventType: 'observation_assessed',
              payload: const <String, dynamic>{
                'retrievalProcessing': <String, dynamic>{
                  'searchedDocumentCount': 3,
                  'processedDocumentCount': 3,
                  'acceptedDocumentCount': 2,
                  'processingSummary': '已核对深圳天气权威来源。',
                },
              },
            ),
            _event(
              seq: 3,
              eventType: 'assistant.answer.delta',
              payload: const <String, dynamic>{'text': '深圳今天适合'},
            ),
            _event(
              seq: 4,
              eventType: 'assistant.answer.final',
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
          assistantRow.runArtifacts['processTimeline'] as List<dynamic>;
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
      'projects structured search queries as retrieval design lines',
      () async {
        final container = _containerWith(
          assistantRepository: _FakeAssistantRepository(
            events: <AssistantStreamEventWire>[
              _event(seq: 1, eventType: 'turn_started'),
              _event(
                seq: 2,
                eventType: 'plan_updated',
                payload: const <String, dynamic>{
                  'understandingSnapshot': <String, dynamic>{
                    'userFacingSummary': '你想确认深圳天气，并安排两天亲子外出。',
                  },
                },
              ),
              _event(
                seq: 3,
                eventType: 'search_query_generated',
                payload: const <String, dynamic>{
                  'searchPlans': <Map<String, dynamic>>[
                    <String, dynamic>{
                      'label': '天气',
                      'query': 'Shenzhen weather forecast',
                    },
                    <String, dynamic>{'label': '亲子活动', 'query': '深圳 五一 亲子 室内'},
                  ],
                },
              ),
              _event(
                seq: 4,
                eventType: 'final_answer',
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
        expect(
          summary.retrievalDesignNarrative,
          contains('天气：Shenzhen weather forecast'),
        );
        expect(summary.retrievalDesignNarrative, contains('亲子活动：深圳 五一 亲子 室内'));
      },
    );

    test('loads app message unread summary', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        ),
        appMessageRepository: _FakeAppMessageRepository(unreadCount: 2),
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
          .openTurnFromAppMessage('atn_test_personal');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.turnId, 'atn_test_personal');
      expect(state.conversationId, 'acv_mock_personal_assistant');
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
      'manages M8 skill subscriptions through assistant repository',
      () async {
        final repository = _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        );
        final container = _containerWith(assistantRepository: repository);
        addTearDown(container.dispose);

        await container
            .read(skillSubscriptionControllerProvider.notifier)
            .createMorningBriefing();
        var state = container.read(skillSubscriptionControllerProvider);
        expect(state.items, hasLength(1));
        expect(state.items.single.status, 'active');

        await container
            .read(skillSubscriptionControllerProvider.notifier)
            .pause(state.items.single.subscriptionId);
        state = container.read(skillSubscriptionControllerProvider);
        expect(state.items.single.status, 'paused');

        await container
            .read(skillSubscriptionControllerProvider.notifier)
            .archive(state.items.single.subscriptionId);
        state = container.read(skillSubscriptionControllerProvider);
        expect(state.items, isEmpty);
      },
    );

    test('creates M9 P0 skill subscriptions from presets', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);

      await container
          .read(skillSubscriptionControllerProvider.notifier)
          .createP0Skill(p0SkillSubscriptionPresets[2]);

      final state = container.read(skillSubscriptionControllerProvider);
      expect(state.items, hasLength(1));
      expect(state.items.single.skillId, 'stock_sentinel');
      expect(state.items.single.trigger.cron, '0 9 * * *');
    });

    test(
      'skill center uses assistant repository for alpha data source',
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
          isFalse,
        );

        await repository.createSkillSubscription(
          skillId: 'stock_sentinel',
          domainId: 'finance',
          rawText: '每天开盘前提醒我关注的股票重大消息',
        );
        container.invalidate(assistantSkillCenterProvider);
        items = await container.read(assistantSkillCenterProvider.future);

        final stock = items
            .where((item) => item.skillId == 'stock_sentinel')
            .single;
        expect(stock.enabled, isTrue);
        expect(stock.statusLabel, '已订阅');
      },
    );

    test('records M9 proactive feedback locally', () {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[],
        ),
      );
      addTearDown(container.dispose);

      container
          .read(personalAssistantStreamControllerProvider.notifier)
          .submitFeedback('too_frequent');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.feedbackMessage, contains('太频繁'));
    });
  });
}

ProviderContainer _containerWith({
  required AssistantRepository assistantRepository,
  AppMessageRepository? appMessageRepository,
}) {
  return ProviderContainer(
    overrides: [
      assistantRepositoryProvider.overrideWithValue(assistantRepository),
      appMessageRepositoryProvider.overrideWithValue(
        appMessageRepository ?? _FakeAppMessageRepository(),
      ),
    ],
  );
}

AssistantStreamEventWire _event({
  required int seq,
  required String eventType,
  Map<String, dynamic> payload = const <String, dynamic>{},
  RuntimeFailureWire? runtimeFailure,
}) {
  return AssistantStreamEventWire(
    eventId: 'evt_$seq',
    conversationId: 'acv_test_personal',
    turnId: 'atn_test_personal',
    seq: seq,
    eventType: eventType,
    payload: payload,
    runtimeFailure: runtimeFailure,
    createdAt: '2026-04-29T00:00:00Z',
  );
}

class _FakeAssistantRepository extends MockAssistantRepository {
  _FakeAssistantRepository({required this.events});

  final List<AssistantStreamEventWire> events;
  int _turnCounter = 0;

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    return const AssistantConversationWire(
      conversationId: 'acv_test_personal',
      userId: 'user_test',
      createdAt: '2026-04-29T00:00:00Z',
      updatedAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    _turnCounter += 1;
    return AssistantTurnEnvelopeWire(
      turnId: _turnCounter == 1
          ? 'atn_test_personal'
          : 'atn_test_personal_$_turnCounter',
      conversationId: conversationId,
      turnType: turnType,
      input: <String, dynamic>{'text': text},
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) {
    return Stream<AssistantStreamEventWire>.fromIterable(events);
  }
}

class _FakeAppMessageRepository implements AppMessageRepository {
  _FakeAppMessageRepository({this.unreadCount = 0});

  final int unreadCount;

  @override
  Future<AppMessageWire> ackAppMessage(String messageId) {
    return getAppMessage(messageId);
  }

  @override
  Future<AppMessageWire> getAppMessage(String messageId) async {
    return AppMessageWire(
      messageId: messageId,
      userId: 'user_test',
      messageType: 'assistant',
      source: 'assistant_turn',
      sourceId: 'atn_test_personal',
      destination: const AppMessageDestinationWire(
        type: 'user',
        id: 'user_test',
      ),
      title: '找私助提醒',
      summary: '测试消息',
      target: const AppMessageTargetWire(
        targetType: 'assistant_turn',
        targetId: 'atn_test_personal',
      ),
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Future<int> getUnreadCount() async {
    return unreadCount;
  }

  @override
  Future<List<AppMessageWire>> listAppMessages({int limit = 20}) async {
    return <AppMessageWire>[await getAppMessage('msg_test_personal')];
  }

  @override
  Future<AppMessageWire> readAppMessage(String messageId) {
    return getAppMessage(messageId);
  }
}

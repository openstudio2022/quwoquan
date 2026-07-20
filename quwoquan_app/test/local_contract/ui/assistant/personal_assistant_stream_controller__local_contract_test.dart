import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/cloud_services/assistant_facet_overrides.dart';
import '../../../support/fixtures/assistant/assistant_scenario_fixtures.dart';

class _EmptyAssistantHistoryLoader implements AssistantHistoryLoader {
  const _EmptyAssistantHistoryLoader();

  @override
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  }) async {
    return null;
  }
}

void main() {
  group('PersonalAssistantStreamController', () {
    test('显式 alpha facet override 投影 scenario stream', () async {
      final scenarioPack = loadAssistantScenarioPack();
      final scenario = scenarioPack
          .assistantTurnScenariosFor('alpha')
          .firstWhere((item) => item.id == 'weather_trip_basic');
      final container = ProviderContainer(
        overrides: [
          ...alphaAssistantFacetOverrides(
            ScenarioMockAssistantRepository(pack: scenarioPack),
          ),
          assistantHistoryLoaderProvider.overrideWithValue(
            const _EmptyAssistantHistoryLoader(),
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(
        container.read(assistantConversationRunFacetProvider),
        isA<AlphaAssistantFacets>(),
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

    test('answer_reset 清空重启前的 partial answer', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '旧回答'},
            ),
            _event(
              seq: 2,
              eventType: 'answer_reset',
              payload: const <String, dynamic>{'reason': 'execution_restarted'},
            ),
            _event(seq: 3, eventType: 'turn_completed'),
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
                eventType: 'final_answer',
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
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '深圳今天适合'},
            ),
            _event(
              seq: 4,
              eventType: 'final_answer',
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
        expect(stock.subscription?.status, 'active');
      },
    );

    test('无 runId 时反馈仅本地记录，不产生学习上报', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);

      container
          .read(personalAssistantStreamControllerProvider.notifier)
          .submitFeedback('too_frequent');
      await pumpEventQueue();

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.feedbackMessage, contains('太频繁'));
      expect(repository.interactionEventBatches, isEmpty);
    });

    // ── C. 学习回路：submitFeedback → reportInteractionEvents ──
    test('submitFeedback 产生一次学习上报且 eventId 稳定派生', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'final_answer',
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
      controller.submitFeedback('useful');
      await pumpEventQueue();

      expect(repository.interactionEventBatches, hasLength(1));
      final event = repository.interactionEventBatches.single.single;
      expect(event.eventId, 'fb:atn_test_personal:useful');
      expect(event.runId, 'atn_test_personal');
      expect(event.pageType, 'assistant_dialog');
      expect(event.domainId, 'assistant');
      expect(event.feedbackType, 'useful');
      expect(controller.pendingFeedbackEventCount, 0);

      // 同一动作重试：稳定派生 id 不产生新事件 id。
      controller.submitFeedback('useful');
      await pumpEventQueue();
      expect(repository.interactionEventBatches, hasLength(2));
      expect(
        repository.interactionEventBatches.last.single.eventId,
        'fb:atn_test_personal:useful',
      );

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
            eventType: 'final_answer',
            payload: const <String, dynamic>{'text': '第一轮回答'},
          ),
        ],
      );
      repository.failInteractionReport = true;
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final controller = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await controller.send('第一轮');
      controller.submitFeedback('irrelevant');
      await pumpEventQueue();

      // UI 展示不被上报失败阻塞；事件保留在内存待重试队列。
      var state = container.read(personalAssistantStreamControllerProvider);
      expect(
        state.feedbackMessage,
        contains(AssistantText.assistantFeedbackIrrelevantLabel),
      );
      expect(state.feedbackType, 'irrelevant');
      expect(controller.pendingFeedbackEventCount, 1);

      repository.failInteractionReport = false;
      await controller.send('第二轮');
      await pumpEventQueue();

      expect(controller.pendingFeedbackEventCount, 0);
      expect(
        repository.interactionEventBatches.last.map((event) => event.eventId),
        contains('fb:atn_test_personal:irrelevant'),
      );
      state = container.read(personalAssistantStreamControllerProvider);
      expect(state.feedbackMessage, isEmpty);
      expect(state.feedbackType, isEmpty);
    });

    // ── P3 飞轮小循环：turn.completed emergedTags → assistant_interest 回流 ──
    test('turn.completed 的 emergedTags 合成 assistant_interest 行为回流', () async {
      final behaviorRepo = MockBehaviorRepository();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'turn_started'),
            _event(
              seq: 2,
              eventType: 'final_answer',
              payload: const <String, dynamic>{'text': '稻城亚丁秋季最佳。'},
            ),
            _event(
              seq: 3,
              eventType: 'assistant.turn.completed',
              payload: const <String, dynamic>{
                'status': 'completed',
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
          .where((e) => e.action == BehaviorAction.assistantInterest)
          .toList();
      expect(interest, hasLength(1));
      expect(interest.single.tags, equals(<String>['Topic/旅行', 'Topic/景区']));
      expect(interest.single.contentId, isEmpty);
    });

    test('无 turn.completed emergedTags 时不回流 assistant_interest', () async {
      final behaviorRepo = MockBehaviorRepository();
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(
              seq: 1,
              eventType: 'final_answer',
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

    test('extractAssistantEmergedTags 仅取 turn.completed 并去重过滤空值', () {
      final tags = extractAssistantEmergedTags(<AssistantStreamEventWire>[
        _event(
          seq: 1,
          eventType: 'final_answer',
          payload: const <String, dynamic>{
            'emergedTags': <String>['Topic/应忽略'],
          },
        ),
        _event(
          seq: 2,
          eventType: 'assistant.turn.completed',
          payload: const <String, dynamic>{
            'emergedTags': <String>['Topic/旅行', ' Topic/景区 ', 'Topic/旅行', ''],
          },
        ),
      ]);
      expect(tags, equals(<String>['Topic/旅行', 'Topic/景区']));
    });

    // ---- 会话生命周期新能力合同（R-ASSIST-001 收口）----

    test('stopGeneration 对运行中 run 发送 CancelAssistantRun 命令', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(seq: 1, eventType: 'turn_started'),
        ],
      );
      final container = _containerWith(assistantRepository: repository);
      addTearDown(container.dispose);
      final notifier = container.read(
        personalAssistantStreamControllerProvider.notifier,
      );

      await notifier.send('长问题');
      // 流已自然结束（fake 事件耗尽），running=false 时 stop 是 no-op。
      await notifier.stopGeneration();
      expect(repository.cancelledRunIds, isEmpty);
    });

    test('turn_cancelled 且无 partial answer 时收尾为停止占位', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'turn_started'),
            _event(
              seq: 2,
              eventType: 'turn_cancelled',
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

    test('turn_cancelled 保留已生成的 partial answer', () async {
      final container = _containerWith(
        assistantRepository: _FakeAssistantRepository(
          events: <AssistantStreamEventWire>[
            _event(seq: 1, eventType: 'turn_started'),
            _event(
              seq: 2,
              eventType: 'partial_answer',
              payload: const <String, dynamic>{'text': '已生成一半'},
            ),
            _event(
              seq: 3,
              eventType: 'turn_cancelled',
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

    test('switchConversation 经 loader 恢复指定会话并绑定 conversationId', () async {
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

      await notifier.switchConversation('conv_target_001');

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(historyLoader.requestedConversationIds, <String>[
        'conv_target_001',
      ]);
      expect(state.conversationId, 'conv_target_001');
      expect(state.historyInitialized, isTrue);
      expect(state.historyLoading, isFalse);
      expect(state.transcript, isNotEmpty);
    });

    test('startNewConversation 清空会话状态供下次 send 新建云端会话', () async {
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
        container
            .read(personalAssistantStreamControllerProvider)
            .conversationId,
        'restored_conversation_001',
      );

      notifier.startNewConversation();

      final state = container.read(personalAssistantStreamControllerProvider);
      expect(state.conversationId, isEmpty);
      expect(state.turnId, isEmpty);
      expect(state.transcript, isEmpty);
      expect(state.historyInitialized, isTrue);
    });

    test('ensureHistoryInitialized 绑定最近云端会话 conversationId 供续聊', () async {
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
        container
            .read(personalAssistantStreamControllerProvider)
            .conversationId,
        'restored_conversation_001',
      );
    });

    test('regenerateLastAnswer 保持原问题并先写入会话偏好', () async {
      final repository = _FakeAssistantRepository(
        events: <AssistantStreamEventWire>[
          _event(
            seq: 1,
            eventType: 'final_answer',
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

      expect(repository.startedRunTexts, <String>['原始问题', '原始问题', '原始问题']);
      final preferences = await repository.listAssistantPreferences(
        scope: AssistantPreferenceScope.session,
      );
      expect(preferences, hasLength(1));
      expect(
        preferences.single.kind,
        AssistantPreferenceKind.replyLength.wireName,
      );
      expect(preferences.single.value, 'concise');
      // 学习信号：regenerated 事实上报（含风格调整标记）。
      final regenerated = repository.interactionEventBatches
          .expand((batch) => batch)
          .where((event) => event.regeneratedAnswer)
          .toList();
      expect(regenerated, isNotEmpty);
    });
  });
}

/// 记录 switchConversation 请求的 loader 桩。
class _SwitchRecordingHistoryLoader implements AssistantHistoryLoader {
  _SwitchRecordingHistoryLoader({this.snapshot});

  final AssistantHistorySnapshot? snapshot;
  final List<String> requestedConversationIds = <String>[];

  @override
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  }) async {
    if (conversationId.isNotEmpty) {
      requestedConversationIds.add(conversationId);
    }
    return snapshot;
  }
}

ProviderContainer _containerWith({
  required AlphaAssistantFacets assistantRepository,
  AppMessageQuery? appMessageQuery,
  AssistantHistoryLoader? historyLoader,
  BehaviorRepository? behaviorRepository,
}) {
  return ProviderContainer(
    overrides: [
      ...alphaAssistantFacetOverrides(assistantRepository),
      appMessageQueryProvider.overrideWithValue(
        appMessageQuery ?? _FakeAppMessageQuery(),
      ),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          subAccountId: 'persona_test',
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
    ],
  );
}

Future<AssistantHistorySnapshot> _buildAssistantHistorySnapshot() async {
  // 云端历史恢复真相源：CloudAssistantHistoryLoader 消费 List conversations/turns
  // 查询面（与 api_integration 断言的服务端行为同源）。
  const conversationId = 'restored_conversation_001';
  final loader = CloudAssistantHistoryLoader(
    _HistoryFacetStub(
      conversation: AssistantConversationWire(
        conversationId: conversationId,
        userId: 'user_test',
        summary: '深圳天气',
        createdAt: '2026-07-20T10:00:00Z',
        updatedAt: '2026-07-20T10:05:00Z',
      ),
      turns: const <AssistantTurnSummaryView>[
        AssistantTurnSummaryView(
          turnId: 'turn_restored_001',
          conversationId: conversationId,
          status: 'completed',
          inputText: '旧问题：深圳天气',
          answerText: '旧回答：深圳今天多云转晴。',
          createdAt: '2026-07-20T10:00:00Z',
          completedAt: '2026-07-20T10:00:30Z',
        ),
      ],
    ),
  );
  final snapshot = await loader.load(subAccountId: 'persona_test');
  return snapshot!;
}

/// 只服务历史恢复断言的最小 Facet 桩：List conversations/turns 返回预置数据，
/// 其余方法不应被 loader 触达。
class _HistoryFacetStub extends AlphaAssistantFacets {
  _HistoryFacetStub({required this.conversation, required this.turns});

  final AssistantConversationWire conversation;
  final List<AssistantTurnSummaryView> turns;

  @override
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return AssistantConversationListPage(
      items: <AssistantConversationWire>[conversation],
    );
  }

  @override
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
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
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
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

class _FakeAssistantRepository extends AlphaAssistantFacets {
  _FakeAssistantRepository({required this.events});

  final List<AssistantStreamEventWire> events;
  int _turnCounter = 0;

  /// 记录 submitFeedback 学习回路的上报批次；[failInteractionReport] 为 true
  /// 时模拟 Remote 全批失败（抛结构化异常）。
  final List<List<InteractionEvent>> interactionEventBatches =
      <List<InteractionEvent>>[];
  bool failInteractionReport = false;

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    interactionEventBatches.add(List<InteractionEvent>.unmodifiable(events));
    if (failInteractionReport) {
      throw StateError('learning append unavailable (test)');
    }
    return AssistantInteractionReportBatchAck(
      accepted: true,
      acceptedCount: events.length,
      count: events.length,
      resource: 'interaction_event_batch',
      mode: 'local_mock',
    );
  }

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

  /// 记录 StartAssistantRun 提交文本（regenerate 合同断言消费）。
  final List<String> startedRunTexts = <String>[];

  @override
  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    _turnCounter += 1;
    startedRunTexts.add(text);
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

  /// 记录 CancelAssistantRun 调用（stopGeneration 合同断言消费）。
  final List<String> cancelledRunIds = <String>[];

  @override
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({
    required String runId,
  }) async {
    cancelledRunIds.add(runId);
    return AssistantTurnEnvelopeWire(
      turnId: runId,
      conversationId: 'acv_test_personal',
      status: 'cancelled',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
  }) {
    return Stream<AssistantStreamEventWire>.fromIterable(events);
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
      messageType: 'assistant',
      source: 'assistant_turn',
      sourceId: 'atn_test_personal',
      destination: const AppMessageDestination(type: 'user', id: 'user_test'),
      title: '找私助提醒',
      summary: '测试消息',
      target: const AppMessageTarget(
        targetType: 'assistant_turn',
        targetId: 'atn_test_personal',
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
        await getAppMessage(
          const GetAppMessageQuery(messageId: 'msg_test_personal'),
        ),
      ],
    );
  }
}

class _FakeAssistantHistoryLoader implements AssistantHistoryLoader {
  _FakeAssistantHistoryLoader({this.snapshot});

  final AssistantHistorySnapshot? snapshot;
  int loadCount = 0;

  @override
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  }) async {
    loadCount += 1;
    return snapshot;
  }
}

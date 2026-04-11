import 'dart:io';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/local_assistant_entry.dart';
import 'package:quwoquan_app/assistant/application/remote_assistant_entry.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_turn_message_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/learning/assistant_learning_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/sync/assistant_sync.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_context_scope_read_view.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_conversation_controller.dart';

List<Map<String, dynamic>> _messageMaps(AssistantConversationController c) {
  return c.transcriptRows
      .map((r) => PersistedTimelineTurnCodec.encode(r))
      .toList(growable: false);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AssistantConversationController', () {
    setUpAll(() {
      TestWidgetsFlutterBinding.ensureInitialized().defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('plugins.flutter.io/path_provider'),
            (MethodCall call) async {
              if (call.method == 'getApplicationDocumentsDirectory') {
                return Directory.systemTemp.path;
              }
              return null;
            },
          );
      TestWidgetsFlutterBinding.ensureInitialized().defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('personal_assistant/native_api'),
            (MethodCall call) async {
              if (call.method == 'getLocalContext') {
                return <String, dynamic>{
                  'city': '深圳',
                  'location': <String, dynamic>{
                    'city': '深圳',
                    'latitude': 22.5431,
                    'longitude': 114.0579,
                    'accuracyM': 120.0,
                  },
                  'device': <String, dynamic>{
                    'locale': 'zh_CN',
                    'timezone': 'Asia/Shanghai',
                  },
                };
              }
              return null;
            },
          );
    });

    testWidgets('initialize 会按分页窗口拆分本地历史并支持继续上拉加载', (tester) async {
      final sessionId = 'local_assistant_test_history';
      final gateway = _FakeAssistantGateway(
        sessions: <AssistantSessionDescriptor>[
          AssistantSessionDescriptor(
            sessionId: sessionId,
            topicTitle: '川西路线',
            isActive: true,
          ),
        ],
        sessionDetails: <String, Map<String, dynamic>>{
          sessionId: <String, dynamic>{
            'topicTitle': '川西路线',
            'messages': _buildHistoryMessages(20),
          },
        },
      );

      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
        ],
      );

      await controller.initialize();
      await tester.pump();

      expect(controller.assistantBackend, AssistantBackend.local);
      expect(controller.assistantTopicTitle, '川西路线');
      expect(controller.transcriptRows, hasLength(18));
      expect(controller.assistantHiddenHistory, hasLength(2));
      expect(controller.showAssistantHistoryPeek, isTrue);
      expect(_messageMaps(controller).first['content'], '用户2');

      await controller.loadOlderHistory();
      await tester.pump();

      expect(controller.transcriptRows, hasLength(20));
      expect(controller.assistantHiddenHistory, isEmpty);
      expect(controller.showAssistantHistoryPeek, isFalse);
      expect(_messageMaps(controller).first['content'], '用户0');
      expect(_messageMaps(controller)[1]['content'], '助理1');
    });

    testWidgets('initialize 会保留 canonical persisted assistant turn 并过滤空白脏消息', (
      tester,
    ) async {
      final sessionId = 'local_assistant_persisted_turn';
      final gateway = _FakeAssistantGateway(
        sessions: <AssistantSessionDescriptor>[
          AssistantSessionDescriptor(
            sessionId: sessionId,
            topicTitle: '周末出行',
            isActive: true,
          ),
        ],
        sessionDetails: <String, Map<String, dynamic>>{
          sessionId: <String, dynamic>{
            'topicTitle': '周末出行',
            'messages': <Map<String, dynamic>>[
              <String, dynamic>{'role': 'user', 'content': '周末去哪玩？'},
              _canonicalHistoryAssistantMessage('可以优先看川西短线。'),
              <String, dynamic>{'role': 'assistant', 'content': ''},
            ],
          },
        },
      );

      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
        ],
      );

      await controller.initialize();
      await tester.pump();

      expect(controller.transcriptRows, hasLength(2));
      expect(
        _messageMaps(controller).last['senderId'],
        AppConceptConstants.assistantSenderId,
      );
      expect(_messageMaps(controller).last['content'], '可以优先看川西短线。');
      expect(controller.assistantHiddenHistory, isEmpty);
      expect(controller.showAssistantHistoryPeek, isFalse);
    });

    testWidgets(
      'sendMessage 会把可见 3 阶段过程轨展示给 UI，同时保留 canonical 4 阶段到最终 assistant 消息',
      (tester) async {
        final gateway = _FastAssistantGateway();
        final entry = _FakeStreamingLocalAssistantEntry();
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(gateway),
            localAssistantEntryProvider.overrideWithValue(entry),
            activePersonaContextProvider.overrideWith((ref) async {
              return const ActivePersonaContextViewData(
                profileSubjectId: 'user_test',
                ownerUserId: 'user_test',
                subAccountId: '',
                subjectType: 'owner',
                displayName: '我',
                avatarUrl: '',
                personaContextVersion: 'test',
              );
            }),
          ],
        );

        unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
        final deadline = DateTime.now().add(const Duration(seconds: 5));
        while (DateTime.now().isBefore(deadline)) {
          await tester.pump(const Duration(milliseconds: 50));
          if (!controller.assistantResponding &&
              controller.transcriptRows.isNotEmpty &&
              _messageMaps(controller).last['senderId'] ==
                  AppConceptConstants.assistantSenderId) {
            break;
          }
        }

        const expectedVisibleSteps = <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ];
        const expectedCanonicalSteps = <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalDesign,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ];

        expect(controller.assistantResponding, isFalse);
        expect(
          controller.currentProcessTimeline
              .map((frame) => frame.stepId)
              .toList(growable: false),
          orderedEquals(expectedVisibleSteps),
        );
        expect(
          controller.currentProcessTimeline.first.detail,
          contains('关注点：天气现状、出门体感'),
        );

        final finalAssistantMessage = _messageMaps(controller).last;
        final visibleTimeline = resolveAssistantProcessTimelineFromMessage(
          finalAssistantMessage,
        );
        expect(
          visibleTimeline.map((frame) => frame.stepId).toList(growable: false),
          orderedEquals(expectedVisibleSteps),
        );
        expect(visibleTimeline.first.detail, contains('关注点：天气现状、出门体感'));
        final persistedTimeline = resolvePersistedAssistantProcessTimeline(
          finalAssistantMessage,
        );
        expect(
          persistedTimeline
              .map((frame) => frame.stepId)
              .toList(growable: false),
          orderedEquals(expectedCanonicalSteps),
        );
        expect(
          (finalAssistantMessage[assistantDisplayMarkdownField] as String?)
              ?.trim(),
          isNotEmpty,
        );
        expect(
          (finalAssistantMessage[assistantDisplayPlainTextField] as String?)
              ?.trim(),
          isNotEmpty,
        );
        expect(
          ((finalAssistantMessage[assistantUiProcessTimelineField] as Map?)
                  ?.cast<String, dynamic>()) ??
              const <String, dynamic>{},
          isNotEmpty,
        );
      },
    );

    testWidgets(
      'completed 未回传 processTimeline 时，仍会把流式阶段累积出的 canonical timeline 落到最终 assistant 消息',
      (tester) async {
        final gateway = _FastAssistantGateway();
        final entry = _FakeStreamingLocalAssistantEntry(
          includeCompletedTimeline: false,
        );
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(gateway),
            localAssistantEntryProvider.overrideWithValue(entry),
            activePersonaContextProvider.overrideWith((ref) async {
              return const ActivePersonaContextViewData(
                profileSubjectId: 'user_test',
                ownerUserId: 'user_test',
                subAccountId: '',
                subjectType: 'owner',
                displayName: '我',
                avatarUrl: '',
                personaContextVersion: 'test',
              );
            }),
          ],
        );

        unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
        final deadline = DateTime.now().add(const Duration(seconds: 5));
        while (DateTime.now().isBefore(deadline)) {
          await tester.pump(const Duration(milliseconds: 50));
          if (!controller.assistantResponding &&
              controller.transcriptRows.isNotEmpty &&
              _messageMaps(controller).last['senderId'] ==
                  AppConceptConstants.assistantSenderId) {
            break;
          }
        }

        final finalAssistantMessage = _messageMaps(controller).last;
        final persistedTimeline = resolvePersistedAssistantProcessTimeline(
          finalAssistantMessage,
        );
        expect(
          persistedTimeline
              .map((frame) => frame.stepId)
              .toList(growable: false),
          orderedEquals(const <ProcessStepId>[
            ProcessStepId.understanding,
            ProcessStepId.retrievalDesign,
            ProcessStepId.retrievalProcessing,
            ProcessStepId.answerOrganization,
          ]),
        );
        expect(
          ((finalAssistantMessage[assistantUiProcessTimelineField] as Map?)
                  ?.cast<String, dynamic>()) ??
              const <String, dynamic>{},
          isNotEmpty,
        );
      },
    );

    testWidgets('completed 回传另一版正文时，会以完成态结果收口已流式展示的最终答案', (tester) async {
      final gateway = _FastAssistantGateway();
      final entry = _FakeStreamingLocalAssistantEntry(
        completedAnswer: '目前体感舒适，适合外出活动。',
      );
      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
          localAssistantEntryProvider.overrideWithValue(entry),
          activePersonaContextProvider.overrideWith((ref) async {
            return const ActivePersonaContextViewData(
              profileSubjectId: 'user_test',
              ownerUserId: 'user_test',
              subAccountId: '',
              subjectType: 'owner',
              displayName: '我',
              avatarUrl: '',
              personaContextVersion: 'test',
            );
          }),
        ],
      );

      unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
      final deadline = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 50));
        if (!controller.assistantResponding &&
            controller.transcriptRows.isNotEmpty &&
            _messageMaps(controller).last['senderId'] ==
                AppConceptConstants.assistantSenderId) {
          break;
        }
      }

      final finalAssistantMessage = _messageMaps(controller).last;
      expect(finalAssistantMessage['content'], equals('目前体感舒适，适合外出活动。'));
      expect(
        finalAssistantMessage[assistantDisplayMarkdownField],
        equals('目前体感舒适，适合外出活动。'),
      );
      expect(
        finalAssistantMessage[assistantDisplayPlainTextField],
        equals('目前体感舒适，适合外出活动。'),
      );
      final runArtifacts =
          (finalAssistantMessage['runArtifacts'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(
        runArtifacts[assistantDisplayMarkdownField],
        equals('目前体感舒适，适合外出活动。'),
      );
      expect(
        runArtifacts[assistantDisplayPlainTextField],
        equals('目前体感舒适，适合外出活动。'),
      );
    });

    testWidgets(
      'completed 存在稳定 displayMarkdown 时，会优先采用 runArtifacts 而不是 raw finalText',
      (tester) async {
        final gateway = _FastAssistantGateway();
        final entry = _FakeStreamingLocalAssistantEntry(
          streamedChunks: const <String>['九寨沟方向备选方案\n'],
          completedAnswer: '九寨沟方向备选方案',
          completedFinalText: '九寨沟方向备选方案\n1. 九寨沟 + 黄龙\n2. 川主寺中转',
          completedDisplayMarkdown:
              '九寨沟方向备选方案\n\n- **九寨沟 + 黄龙**：适合第一次走经典主线。\n- **川主寺中转**：适合更看重交通节奏。',
          completedDisplayPlainText:
              '九寨沟方向备选方案。九寨沟 + 黄龙适合第一次走经典主线；川主寺中转适合更看重交通节奏。',
        );
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(gateway),
            localAssistantEntryProvider.overrideWithValue(entry),
            activePersonaContextProvider.overrideWith((ref) async {
              return const ActivePersonaContextViewData(
                profileSubjectId: 'user_test',
                ownerUserId: 'user_test',
                subAccountId: '',
                subjectType: 'owner',
                displayName: '我',
                avatarUrl: '',
                personaContextVersion: 'test',
              );
            }),
          ],
        );

        unawaited(
          controller.sendMessage(text: '九寨沟方向给我两个备选', viewportWidth: 390),
        );
        final deadline = DateTime.now().add(const Duration(seconds: 5));
        while (DateTime.now().isBefore(deadline)) {
          await tester.pump(const Duration(milliseconds: 50));
          if (!controller.assistantResponding &&
              controller.transcriptRows.isNotEmpty &&
              _messageMaps(controller).last['senderId'] ==
                  AppConceptConstants.assistantSenderId) {
            break;
          }
        }

        final finalAssistantMessage = _messageMaps(controller).last;
        expect(finalAssistantMessage['content'], contains('第一次走经典主线'));
        expect(
          finalAssistantMessage['content'],
          isNot(contains('1. 九寨沟 + 黄龙\n2. 川主寺中转')),
        );
        expect(
          finalAssistantMessage[assistantDisplayMarkdownField],
          contains('第一次走经典主线'),
        );
        expect(
          finalAssistantMessage[assistantDisplayPlainTextField],
          contains('第一次走经典主线'),
        );
        final runArtifacts =
            (finalAssistantMessage['runArtifacts'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        expect(
          runArtifacts[assistantDisplayMarkdownField],
          contains('第一次走经典主线'),
        );
        expect(
          runArtifacts[assistantDisplayPlainTextField],
          contains('第一次走经典主线'),
        );
      },
    );

    testWidgets('canonical answer gate 未就绪时不会误开 UI answer gate', (
      tester,
    ) async {
      final gateway = _FastAssistantGateway();
      final entry = _FakeStreamingLocalAssistantEntry(
        completedFinalAnswerReady: false,
      );
      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
          localAssistantEntryProvider.overrideWithValue(entry),
          activePersonaContextProvider.overrideWith((ref) async {
            return const ActivePersonaContextViewData(
              profileSubjectId: 'user_test',
              ownerUserId: 'user_test',
              subAccountId: '',
              subjectType: 'owner',
              displayName: '我',
              avatarUrl: '',
              personaContextVersion: 'test',
            );
          }),
        ],
      );

      unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
      final deadline = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 50));
        if (!controller.assistantResponding &&
            controller.transcriptRows.isNotEmpty &&
            _messageMaps(controller).last['senderId'] ==
                AppConceptConstants.assistantSenderId) {
          break;
        }
      }

      expect(controller.answerGateOpen, isFalse);
      expect(_messageMaps(controller).last['content'], isNotEmpty);
    });

    testWidgets('sendMessage 在稀疏 blocked 终态下仍保留已流式展示的 query design 与答案正文', (
      tester,
    ) async {
      final gateway = _FastAssistantGateway();
      final entry = _FakeStreamingLocalAssistantEntry(
        completedFinalAnswerReady: false,
        completedTimeline: <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.blocked,
            headline: '当前证据还不够稳定。',
            retrievalProcessing: const RetrievalProcessingSnapshot(
              processingSummary: '当前证据还不够稳定。',
            ),
          ),
        ],
      );
      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
          localAssistantEntryProvider.overrideWithValue(entry),
          activePersonaContextProvider.overrideWith((ref) async {
            return const ActivePersonaContextViewData(
              profileSubjectId: 'user_test',
              ownerUserId: 'user_test',
              subAccountId: '',
              subjectType: 'owner',
              displayName: '我',
              avatarUrl: '',
              personaContextVersion: 'test',
            );
          }),
        ],
      );

      unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
      final deadline = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 50));
        if (!controller.assistantResponding &&
            controller.transcriptRows.isNotEmpty &&
            _messageMaps(controller).last['senderId'] ==
                AppConceptConstants.assistantSenderId) {
          break;
        }
      }

      final finalAssistantMessage = _messageMaps(controller).last;
      final displayState = resolvePersistedAssistantDisplayState(
        finalAssistantMessage,
      );
      final persistedTimeline = resolvePersistedAssistantProcessTimeline(
        finalAssistantMessage,
      );
      expect(controller.answerGateOpen, isFalse);
      expect(
        persistedTimeline.map((frame) => frame.stepId).toList(growable: false),
        orderedEquals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalDesign,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ]),
      );
      expect(
        displayState.process.blocks.any(
          (block) =>
              block.blockId == 'understanding_summary' &&
              block.title.contains('实时天气结果'),
        ),
        isTrue,
      );
      expect(
        displayState.process.blocks.any(
          (block) =>
              block.blockId == 'retrieval_query_design' &&
              block.items.any((item) => item.body.contains('天气现状和出门建议两路来核对')),
        ),
        isTrue,
      );
      expect(
        renderAnswerBlocksToMarkdown(displayState.answer.blocks),
        isNotEmpty,
      );
    });

    testWidgets('sendMessage 在稀疏终态下仍保留 understanding resolutionItems', (
      tester,
    ) async {
      final gateway = _FastAssistantGateway();
      final streamedTimelines = <List<ProcessTimelineFrame>>[
        <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
            headline: '我先把相对时间和市场范围落清。',
            understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
              userFacingSummary: '我先把相对时间和市场范围落清。',
              resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
                RunArtifactsUnderstandingResolutionItem(
                  kind: 'temporal_anchor',
                  title: '时间锚点',
                  detail: '昨天已对齐到 2026年4月9日。',
                  visibleInUnderstanding: true,
                ),
                RunArtifactsUnderstandingResolutionItem(
                  kind: 'geo_anchor',
                  title: '地理锚点',
                  detail: '默认按中国股市/A股理解。',
                  visibleInUnderstanding: true,
                ),
              ],
            ),
          ),
        ],
        <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
            headline: '我先把相对时间和市场范围落清。',
            understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
              userFacingSummary: '我先把相对时间和市场范围落清。',
              resolutionItems: <RunArtifactsUnderstandingResolutionItem>[
                RunArtifactsUnderstandingResolutionItem(
                  kind: 'temporal_anchor',
                  title: '时间锚点',
                  detail: '昨天已对齐到 2026年4月9日。',
                  visibleInUnderstanding: true,
                ),
              ],
            ),
          ),
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.active,
            headline: '我先筛一轮高相关结果。',
            retrievalProcessing: const RetrievalProcessingSnapshot(
              processingSummary: '我先筛一轮高相关结果。',
            ),
          ),
        ],
      ];
      final entry = _FakeStreamingLocalAssistantEntry(
        streamedTimelines: streamedTimelines,
        completedFinalAnswerReady: false,
        completedTimeline: <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.blocked,
            headline: '当前证据还不够稳定。',
            retrievalProcessing: const RetrievalProcessingSnapshot(
              processingSummary: '当前证据还不够稳定。',
            ),
          ),
        ],
      );
      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
          localAssistantEntryProvider.overrideWithValue(entry),
          activePersonaContextProvider.overrideWith((ref) async {
            return const ActivePersonaContextViewData(
              profileSubjectId: 'user_test',
              ownerUserId: 'user_test',
              subAccountId: '',
              subjectType: 'owner',
              displayName: '我',
              avatarUrl: '',
              personaContextVersion: 'test',
            );
          }),
        ],
      );

      unawaited(controller.sendMessage(text: '昨天A股为什么大涨', viewportWidth: 390));
      final deadline = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 50));
        if (!controller.assistantResponding &&
            controller.transcriptRows.isNotEmpty &&
            _messageMaps(controller).last['senderId'] ==
                AppConceptConstants.assistantSenderId) {
          break;
        }
      }

      final finalAssistantMessage = _messageMaps(controller).last;
      final displayState = resolvePersistedAssistantDisplayState(
        finalAssistantMessage,
      );
      final understandingSnapshot =
          resolveAssistantUnderstandingSnapshotFromMessage(
            finalAssistantMessage,
          );
      expect(
        displayState.process.blocks.any(
          (block) =>
              block.blockId == 'understanding_resolution_items' &&
              block.items.any((item) => item.body.contains('2026年4月9日')) &&
              block.items.any((item) => item.body.contains('中国股市/A股')),
        ),
        isTrue,
      );
      expect(
        understandingSnapshot.resolutionItems.any(
          (item) => item.detail.contains('2026年4月9日'),
        ),
        isTrue,
      );
      expect(
        understandingSnapshot.resolutionItems.any(
          (item) => item.detail.contains('中国股市/A股'),
        ),
        isTrue,
      );
    });

    testWidgets(
      'sendMessage 完成后 remount/reinitialize 仍恢复 query design、timeline 与答案',
      (tester) async {
        final initialGateway = _FakeAssistantGateway(
          sessions: const <AssistantSessionDescriptor>[],
          sessionDetails: const <String, Map<String, dynamic>>{},
        );
        final entry = _FakeStreamingLocalAssistantEntry();
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(initialGateway),
            localAssistantEntryProvider.overrideWithValue(entry),
            activePersonaContextProvider.overrideWith((ref) async {
              return const ActivePersonaContextViewData(
                profileSubjectId: 'user_test',
                ownerUserId: 'user_test',
                subAccountId: '',
                subjectType: 'owner',
                displayName: '我',
                avatarUrl: '',
                personaContextVersion: 'test',
              );
            }),
          ],
        );

        await controller.initialize();
        await tester.pump();
        final sessionId = controller.assistantRuntimeSessionId;

        unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
        final firstDeadline = DateTime.now().add(const Duration(seconds: 5));
        while (DateTime.now().isBefore(firstDeadline)) {
          await tester.pump(const Duration(milliseconds: 50));
          if (!controller.assistantResponding &&
              controller.transcriptRows.isNotEmpty &&
              _messageMaps(controller).last['senderId'] ==
                  AppConceptConstants.assistantSenderId) {
            break;
          }
        }

        final persistedAssistantMessage = _messageMaps(controller).last;
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();

        final reloadGateway = _FakeAssistantGateway(
          sessions: <AssistantSessionDescriptor>[
            AssistantSessionDescriptor(
              sessionId: sessionId,
              topicTitle: '天气回放',
              isActive: true,
            ),
          ],
          sessionDetails: <String, Map<String, dynamic>>{
            sessionId: <String, dynamic>{
              'topicTitle': '天气回放',
              'messages': <Map<String, dynamic>>[
                <String, dynamic>{'role': 'user', 'content': '深圳天气怎么样'},
                persistedAssistantMessage,
              ],
            },
          },
        );
        final reloadedController = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(reloadGateway),
          ],
        );

        await reloadedController.initialize();
        await tester.pump();

        final reloadedMessage = _messageMaps(reloadedController).last;
        final reloadedDisplayState = resolvePersistedAssistantDisplayState(
          reloadedMessage,
        );
        final reloadedTimeline = resolvePersistedAssistantProcessTimeline(
          reloadedMessage,
        );
        expect(reloadedController.assistantResponding, isFalse);
        expect(
          reloadedTimeline.map((frame) => frame.stepId).toList(growable: false),
          orderedEquals(const <ProcessStepId>[
            ProcessStepId.understanding,
            ProcessStepId.retrievalDesign,
            ProcessStepId.retrievalProcessing,
            ProcessStepId.answerOrganization,
          ]),
        );
        expect(
          reloadedDisplayState.process.blocks.any(
            (block) =>
                block.blockId == 'retrieval_query_design' &&
                block.items.any((item) => item.body.contains('天气现状和出门建议两路来核对')),
          ),
          isTrue,
        );
        expect(
          renderAnswerBlocksToMarkdown(reloadedDisplayState.answer.blocks),
          contains('深圳今天晴'),
        );
      },
    );

    testWidgets(
      'remote provider 注入后 completed turn 仍会落成 canonical persisted assistant turn',
      (tester) async {
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => true),
            assistantGatewayProvider.overrideWithValue(
              _FakeAssistantGateway(
                sessions: const <AssistantSessionDescriptor>[],
                sessionDetails: const <String, Map<String, dynamic>>{},
              ),
            ),
            remoteAssistantEntryProvider.overrideWithValue(
              _FakeStreamingRemoteAssistantEntry(),
            ),
            activePersonaContextProvider.overrideWith((ref) async {
              return const ActivePersonaContextViewData(
                profileSubjectId: 'user_test',
                ownerUserId: 'user_test',
                subAccountId: '',
                subjectType: 'owner',
                displayName: '我',
                avatarUrl: '',
                personaContextVersion: 'test',
              );
            }),
          ],
        );

        await controller.initialize();
        await tester.pump();
        expect(controller.assistantBackend, AssistantBackend.remote);

        unawaited(controller.sendMessage(text: '深圳天气怎么样', viewportWidth: 390));
        final deadline = DateTime.now().add(const Duration(seconds: 5));
        while (DateTime.now().isBefore(deadline)) {
          await tester.pump(const Duration(milliseconds: 50));
          if (!controller.assistantResponding &&
              controller.transcriptRows.isNotEmpty &&
              _messageMaps(controller).last['senderId'] ==
                  AppConceptConstants.assistantSenderId) {
            break;
          }
        }

        final finalAssistantMessage = _messageMaps(controller).last;
        final displayState = resolvePersistedAssistantDisplayState(
          finalAssistantMessage,
        );
        expect(
          finalAssistantMessage[assistantTurnSchemaVersionField],
          isNotNull,
        );
        expect(finalAssistantMessage[assistantDisplayStateField], isA<Map>());
        expect(
          finalAssistantMessage[assistantProcessTimelineField],
          isA<List>(),
        );
        expect(
          displayState.process.blocks.any(
            (block) =>
                block.blockId == 'retrieval_query_design' &&
                block.items.any((item) => item.body.contains('天气现状和出门建议两路来核对')),
          ),
          isTrue,
        );
        expect(
          renderAnswerBlocksToMarkdown(displayState.answer.blocks),
          contains('深圳今天晴'),
        );
      },
    );

    testWidgets('sendRewrite 与 sendMessage 使用同一 completed merge 规则', (
      tester,
    ) async {
      final gateway = _FastAssistantGateway();
      final entry = _FakeStreamingLocalAssistantEntry(
        completedFinalAnswerReady: false,
        completedTimeline: <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.blocked,
            headline: '当前证据还不够稳定。',
            retrievalProcessing: const RetrievalProcessingSnapshot(
              processingSummary: '当前证据还不够稳定。',
            ),
          ),
        ],
      );
      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
          localAssistantEntryProvider.overrideWithValue(entry),
          activePersonaContextProvider.overrideWith((ref) async {
            return const ActivePersonaContextViewData(
              profileSubjectId: 'user_test',
              ownerUserId: 'user_test',
              subAccountId: '',
              subjectType: 'owner',
              displayName: '我',
              avatarUrl: '',
              personaContextVersion: 'test',
            );
          }),
        ],
      );

      unawaited(
        controller.sendRewrite(
          query: '深圳天气怎么样',
          rewrite: const RewriteInstruction(
            mode: RewriteMode.concise,
            originalQuery: '深圳天气怎么样',
            previousAnswer: '上一版回答',
          ),
        ),
      );
      final deadline = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 50));
        if (!controller.assistantResponding &&
            controller.transcriptRows.isNotEmpty &&
            _messageMaps(controller).last['senderId'] ==
                AppConceptConstants.assistantSenderId) {
          break;
        }
      }

      final finalAssistantMessage = _messageMaps(controller).last;
      final displayState = resolvePersistedAssistantDisplayState(
        finalAssistantMessage,
      );
      expect(
        displayState.process.blocks.any(
          (block) =>
              block.blockId == 'understanding_summary' &&
              block.title.contains('实时天气结果'),
        ),
        isTrue,
      );
      expect(
        displayState.process.blocks.any(
          (block) =>
              block.blockId == 'retrieval_query_design' &&
              block.items.any((item) => item.body.contains('天气现状和出门建议两路来核对')),
        ),
        isTrue,
      );
      expect(
        renderAnswerBlocksToMarkdown(displayState.answer.blocks),
        isNotEmpty,
      );
    });

    testWidgets(
      'buildJourneyViewModel 会把 query design 与答案阶段摘要一并投影进 displayState',
      (tester) async {
        final controller = await _mountController(
          tester,
          overrides: [
            assistantRemoteConfiguredProvider.overrideWith((ref) => false),
            assistantGatewayProvider.overrideWithValue(_FastAssistantGateway()),
          ],
        );

        final viewModel = controller.buildJourneyViewModel(
          journey: const AssistantJourney(
            readiness: AssistantJourneyReadiness(finalAnswerReady: true),
          ),
          processTimeline: const <ProcessTimelineFrame>[
            ProcessTimelineFrame(
              frameId: 'u',
              stepId: ProcessStepId.understanding,
              status: JourneyStageStatus.completed,
            ),
            ProcessTimelineFrame(
              frameId: 'r',
              stepId: ProcessStepId.retrievalProcessing,
              status: JourneyStageStatus.completed,
            ),
            ProcessTimelineFrame(
              frameId: 'a',
              stepId: ProcessStepId.answerOrganization,
              status: JourneyStageStatus.completed,
            ),
          ],
          isRunning: false,
          understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
            queryDesignSummary: '交易日确认：先把相对时间落成具体日期。',
            queryGroups: <RunArtifactsUnderstandingQueryGroup>[
              RunArtifactsUnderstandingQueryGroup(
                dimension: '交易日确认',
                queries: <String>['2026-04-07 A股 大涨 原因'],
                why: '先把相对时间落成具体日期。',
              ),
            ],
          ),
          retrievalProcessing: const RetrievalProcessingSnapshot(
            processingSummary: '已经筛出可直接支撑结论的线索。',
            acceptedDocumentCount: 1,
          ),
          answerProcessing: const RunArtifactsAnswerProcessing(
            readinessSummary: '我开始把已确认的信息整理成回答。',
          ),
        );

        expect(viewModel.displayState.process.finalAnswerReady, isTrue);
        expect(
          viewModel.displayState.process.blocks.any(
            (block) => block.blockId == 'retrieval_query_design',
          ),
          isTrue,
        );
        expect(
          viewModel.displayState.process.blocks.any(
            (block) =>
                block.blockId == 'answer_summary' &&
                block.title.contains('整理成回答'),
          ),
          isTrue,
        );
      },
    );

    test('contextScope 读视图与 run 请求使用的键一致', () {
      final raw = <String, dynamic>{
        'privacyPolicy': <String, dynamic>{'webAccessMode': 'limited'},
        'pageType': 'discovery',
        'userTags': <dynamic>[' t1 ', 't2'],
      };
      final view = AssistantContextScopeReadView(raw);
      expect(
        (raw['privacyPolicy'] as Map).cast<String, dynamic>(),
        view.privacyPolicy,
      );
      expect(view.pageType, 'discovery');
      expect(view.normalizedUserTags, ['t1', 't2']);
    });
  });
}

Future<AssistantConversationController> _mountController(
  WidgetTester tester, {
  required dynamic overrides,
}) async {
  final completer = Completer<AssistantConversationController>();

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantLearningServiceProvider.overrideWithValue(
          _NoopAssistantLearningService(),
        ),
        ...overrides,
      ],
      child: MaterialApp(
        home: _ControllerHarness(
          onReady: (controller) {
            if (!completer.isCompleted) {
              completer.complete(controller);
            }
          },
        ),
      ),
    ),
  );

  return completer.future;
}

List<Map<String, dynamic>> _buildHistoryMessages(int count) {
  return List<Map<String, dynamic>>.generate(count, (index) {
    final isUser = index.isEven;
    return <String, dynamic>{
      'role': isUser ? 'user' : 'assistant',
      'content': isUser ? '用户$index' : '助理$index',
    };
  });
}

Map<String, dynamic> _canonicalHistoryAssistantMessage(String content) {
  return <String, dynamic>{
    'role': 'assistant',
    'content': '',
    ...buildPersistedAssistantTurnFields(
      journey: const AssistantJourney(),
      displayMarkdown: content,
      displayPlainText: content,
      followupPrompt: '',
      actionHints: const <String>[],
      elapsedMs: 800,
    ),
  };
}

class _ControllerHarness extends ConsumerStatefulWidget {
  const _ControllerHarness({required this.onReady});

  final ValueChanged<AssistantConversationController> onReady;

  @override
  ConsumerState<_ControllerHarness> createState() => _ControllerHarnessState();
}

class _ControllerHarnessState extends ConsumerState<_ControllerHarness> {
  late final AssistantConversationController controller;

  @override
  void initState() {
    super.initState();
    controller = AssistantConversationController(ref: ref);
    widget.onReady(controller);
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

class _FakeAssistantGateway extends AssistantGateway {
  _FakeAssistantGateway({required this.sessions, required this.sessionDetails})
    : super(AssistantRuntime.createForTest());

  final List<AssistantSessionDescriptor> sessions;
  final Map<String, Map<String, dynamic>> sessionDetails;

  @override
  Future<List<AssistantSessionDescriptor>> listSessions() async => sessions;

  @override
  Future<AssistantSessionWireDetail?> sessionDetail(String sessionId) async {
    final raw = sessionDetails[sessionId];
    if (raw == null) return null;
    return AssistantSessionWireDetail.fromJson(raw);
  }

  @override
  Future<void> ensureRemoteConfigLoaded() async {}
}

class _FastAssistantGateway extends AssistantGateway {
  _FastAssistantGateway() : super(AssistantRuntime.createForTest());

  @override
  Future<void> ensureRemoteConfigLoaded() async {}
}

class _NoopAssistantLearningService extends AssistantLearningService {
  _NoopAssistantLearningService()
    : super(
        store: AssistantLearningStore(
          storagePath:
              '${Directory.systemTemp.path}/assistant_learning_test.json',
        ),
        syncGateway: AssistantSyncGateway(
          _NoopAssistantSyncAdapter(),
          AssistantSyncMode.localMock,
        ),
      );

  @override
  Future<void> recordInteraction({
    required String runId,
    required String traceId,
    required String userId,
    required String sessionId,
    required String pageType,
    required String queryText,
    required String answerText,
    required List<String> userTags,
    required int durationMs,
    String domainId = '',
    String explicitThumb = 'none',
    List<String> explicitReasonCodes = const <String>[],
    bool copiedAnswer = false,
    bool sharedAnswer = false,
    bool favoritedAnswer = false,
    bool regeneratedAnswer = false,
    bool styleAdjusted = false,
    bool modelSwitched = false,
    bool referenceOpened = false,
    bool interrupted = false,
    String feedbackTargetMessageId = '',
    String correctionText = '',
  }) async {}

  @override
  Future<void> recordExplicitFeedback({
    required String runId,
    required String traceId,
    required String userId,
    required String sessionId,
    required String pageType,
    required String queryText,
    required String answerText,
    required List<String> userTags,
    required String explicitThumb,
    required List<String> explicitReasonCodes,
    String domainId = '',
    String correctionText = '',
    String feedbackTargetMessageId = '',
  }) async {}

  @override
  Future<Map<String, dynamic>> latestScoreSnapshot() async {
    return const <String, dynamic>{};
  }
}

class _NoopAssistantSyncAdapter extends AssistantSyncAdapter {
  _NoopAssistantSyncAdapter();

  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return const AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.policy,
      message: 'noop',
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
      message: 'noop',
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
      message: 'noop',
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
      message: 'noop',
    );
  }
}

class _FakeStreamingLocalAssistantEntry extends LocalAssistantEntry {
  _FakeStreamingLocalAssistantEntry({
    this.includeCompletedTimeline = true,
    this.streamedTimelines,
    this.completedTimeline,
    this.completedAnswer = '深圳今天晴，轻装出门更合适。',
    this.streamedChunks = const <String>['深圳今天晴，', '轻装出门更合适。'],
    this.completedFinalText,
    this.completedDisplayMarkdown,
    this.completedDisplayPlainText,
    this.completedFinalAnswerReady = true,
  }) : super(
         assistantGateway: _FastAssistantGateway(),
         requestPolicy: const AssistantRequestPolicy(),
       );

  final bool includeCompletedTimeline;
  final List<List<ProcessTimelineFrame>>? streamedTimelines;
  final List<ProcessTimelineFrame>? completedTimeline;
  final String completedAnswer;
  final List<String> streamedChunks;
  final String? completedFinalText;
  final String? completedDisplayMarkdown;
  final String? completedDisplayPlainText;
  final bool completedFinalAnswerReady;

  @override
  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
  }) async* {
    final canonicalTimelines = streamedTimelines ?? _fourStageTimelines();
    final visibleTimelines = canonicalTimelines
        .map(buildVisibleProcessTimeline)
        .toList(growable: false);
    for (final timeline in visibleTimelines) {
      yield AssistantRunStreamEvent.processTimeline(timeline);
    }
    for (final chunk in streamedChunks) {
      yield AssistantRunStreamEvent.answerDelta(chunk);
    }
    yield AssistantRunStreamEvent.completed(
      _completedAssistantRunResponse(
        completedTimeline ?? canonicalTimelines.last,
        includeTimeline: includeCompletedTimeline,
        answer: completedAnswer,
        finalText: completedFinalText,
        displayMarkdown: completedDisplayMarkdown,
        displayPlainText: completedDisplayPlainText,
        finalAnswerReady: completedFinalAnswerReady,
      ),
    );
  }
}

class _FakeStreamingRemoteAssistantEntry extends RemoteAssistantEntry {
  _FakeStreamingRemoteAssistantEntry({
    this.includeCompletedTimeline = true,
    this.streamedTimelines,
    this.completedTimeline,
    this.completedAnswer = '深圳今天晴，轻装出门更合适。',
    this.streamedChunks = const <String>['深圳今天晴，', '轻装出门更合适。'],
    this.completedFinalText,
    this.completedDisplayMarkdown,
    this.completedDisplayPlainText,
    this.completedFinalAnswerReady = true,
  }) : super(
         openClawBridge: OpenClawBridge(baseUrl: ''),
         requestPolicy: const AssistantRequestPolicy(),
       );

  final bool includeCompletedTimeline;
  final List<List<ProcessTimelineFrame>>? streamedTimelines;
  final List<ProcessTimelineFrame>? completedTimeline;
  final String completedAnswer;
  final List<String> streamedChunks;
  final String? completedFinalText;
  final String? completedDisplayMarkdown;
  final String? completedDisplayPlainText;
  final bool completedFinalAnswerReady;

  @override
  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
  }) async* {
    final canonicalTimelines = streamedTimelines ?? _fourStageTimelines();
    final visibleTimelines = canonicalTimelines
        .map(buildVisibleProcessTimeline)
        .toList(growable: false);
    for (final timeline in visibleTimelines) {
      yield AssistantRunStreamEvent.processTimeline(timeline);
    }
    for (final chunk in streamedChunks) {
      yield AssistantRunStreamEvent.answerDelta(chunk);
    }
    yield AssistantRunStreamEvent.completed(
      _completedAssistantRunResponse(
        completedTimeline ?? canonicalTimelines.last,
        includeTimeline: includeCompletedTimeline,
        answer: completedAnswer,
        finalText: completedFinalText,
        displayMarkdown: completedDisplayMarkdown,
        displayPlainText: completedDisplayPlainText,
        finalAnswerReady: completedFinalAnswerReady,
      ),
    );
  }
}

AssistantRunResponse _completedAssistantRunResponse(
  List<ProcessTimelineFrame> canonicalTimeline, {
  bool includeTimeline = true,
  String answer = '深圳今天晴，轻装出门更合适。',
  String? finalText,
  String? displayMarkdown,
  String? displayPlainText,
  bool finalAnswerReady = true,
}) {
  final effectiveFinalText = finalText ?? answer;
  final effectiveDisplayMarkdown = displayMarkdown ?? answer;
  final effectiveDisplayPlainText = displayPlainText ?? answer;
  return AssistantRunResponse(
    finalText: effectiveFinalText,
    traces: const [],
    structuredResponse: <String, dynamic>{
      'contractId': kAssistantTurnCurrentContractId,
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '天气结论已经整理好了。',
      'decision': const <String, dynamic>{
        'nextAction': 'answer',
        'confidence': 0.91,
        'reasoning': '关键信息已经齐备',
      },
      assistantAnswerGateDecisionField: <String, dynamic>{
        'eligible': finalAnswerReady,
        'finalAnswerReady': finalAnswerReady,
        'reasonCode': finalAnswerReady
            ? 'evidence_ready'
            : 'need_more_evidence',
        'reason': finalAnswerReady ? '资料已经齐备。' : '当前证据还不够稳定。',
        'nextAction': finalAnswerReady ? 'answer' : 'abort',
        'answerEligibility': finalAnswerReady ? 'answer' : 'blocked',
        'renderable': true,
        'retrievalReady': finalAnswerReady,
        'terminalPayloadComplete': true,
        'degraded': false,
        'incomplete': false,
      },
      assistantRetrievalOutcomeField: <String, dynamic>{
        'status': finalAnswerReady ? 'ready' : 'need_more_evidence',
        'summary': finalAnswerReady ? '资料已经齐备。' : '当前证据还不够稳定。',
        'terminalPayloadComplete': true,
        'degraded': false,
      },
      'userMarkdown': effectiveDisplayMarkdown,
      'result': <String, dynamic>{
        'text': effectiveDisplayPlainText,
        'summary': effectiveDisplayPlainText,
        'interpretation': '天气结论',
        'actionHints': const <String>[],
      },
      'answerProcessing': const <String, dynamic>{
        'readinessSummary': '天气结论已经可以稳定输出。',
        'keyFacts': <String>['天气结论已经整理完成'],
        'missingDimensions': <String>[],
        'retrieveMoreReason': '',
      },
      'runArtifacts': <String, dynamic>{
        'displayMarkdown': effectiveDisplayMarkdown,
        'displayPlainText': effectiveDisplayPlainText,
        if (includeTimeline)
          'processTimeline': canonicalTimeline
              .map((item) => item.toJson())
              .toList(growable: false),
      },
    },
  );
}

List<List<ProcessTimelineFrame>> _fourStageTimelines() {
  final understanding = buildProcessTimelineFrame(
    stepId: ProcessStepId.understanding,
    status: JourneyStageStatus.completed,
    headline: '我先确认你现在最需要的是实时天气结果。',
    detail: '关注点：天气现状、出门体感',
    understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
      intentSummary: '我先确认你现在最需要的是实时天气结果。',
      userFacingSummary: '我先确认你现在最需要的是实时天气结果。',
      concernPoints: <String>['天气现状', '出门体感'],
    ),
  );
  final retrievalDesign = buildProcessTimelineFrame(
    stepId: ProcessStepId.retrievalDesign,
    status: JourneyStageStatus.completed,
    headline: '我会先按天气现状和出门建议两路来核对。',
    understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
      queryDesignSummary: '我会先按天气现状和出门建议两路来核对。',
      queryGroups: <RunArtifactsUnderstandingQueryGroup>[
        RunArtifactsUnderstandingQueryGroup(
          dimension: '天气现状',
          queries: <String>['深圳 实时天气', '深圳 当前体感'],
          why: '先确认现在的天气和出门体感。',
        ),
      ],
    ),
  );
  final retrievalProcessing = buildProcessTimelineFrame(
    stepId: ProcessStepId.retrievalProcessing,
    status: JourneyStageStatus.completed,
    headline: '能直接回答的关键信息已经收拢好了。',
    retrievalProcessing: const RetrievalProcessingSnapshot(
      processingSummary: '能直接回答的关键信息已经收拢好了。',
    ),
  );
  final answerOrganization = buildProcessTimelineFrame(
    stepId: ProcessStepId.answerOrganization,
    status: JourneyStageStatus.completed,
    headline: '我把结果压成一句直接结论和一条简洁建议。',
    answerProcessing: const RunArtifactsAnswerProcessing(
      readinessSummary: '我把结果压成一句直接结论和一条简洁建议。',
    ),
  );
  return <List<ProcessTimelineFrame>>[
    <ProcessTimelineFrame>[understanding],
    <ProcessTimelineFrame>[understanding, retrievalDesign],
    <ProcessTimelineFrame>[understanding, retrievalDesign, retrievalProcessing],
    <ProcessTimelineFrame>[
      understanding,
      retrievalDesign,
      retrievalProcessing,
      answerOrganization,
    ],
  ];
}

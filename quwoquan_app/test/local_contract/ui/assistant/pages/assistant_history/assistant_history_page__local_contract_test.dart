// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
/// assistantHistory user_acceptance（B8 阶段 4a：真实页面 pump 验收）。
///
/// surface: assistantHistory · owner: assistant · route: chatDetail
/// 本文件替代旧「证据文件路径存在性断言」伪验收。承载关系说明：
/// assistantHistory surface（私助记录抽屉与分页）由 `PersonalAssistantConversationPage`
/// 承载：进入页面时经 `assistantHistoryLoaderProvider`
/// （`CloudAssistantHistoryLoader`，消费 ListAssistantConversations /
/// ListConversationTurns 云端查询面）恢复最近会话 transcript，
/// 再在同一时间线上继续新 turn；顶栏历史按钮打开会话抽屉可切换/新建会话。
/// 四类必测 case：
/// - load_success：历史 snapshot 恢复后真实渲染到时间线（历史问答上屏）；
/// - empty_permission_error：loader 抛 CloudException → 按「无历史」空态
///   继续（不崩溃、不伪造历史数据、新会话不被阻断，3b 容忍降级语义）；
/// - primary_cta：历史恢复后继续发送新消息（页面主动作），历史行保留在前、
///   新 turn 追加在后，且 loader 不重复加载；
/// - trace_context：页面曝光进入 VisitRecorder，历史恢复后 turn 上下文推进。
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_conversation_inline_error.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime_failure_fixtures.dart';

const _historyQuestion = '旧问题：深圳天气';
const _historyAnswer = '旧回答：深圳今天多云转晴。[1](https://example.com/weather)';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProvider();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_assistant_history_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  test('terminal_history：failed 与 cancelled 终态不被恢复成空白历史', () async {
    const conversationId = 'terminal_state_history';
    final loader = CloudAssistantHistoryLoader(
      _HistoryQueryFacetStub(
        conversation: const AssistantConversationWire(
          conversationId: conversationId,
          userId: 'user_uat',
          summary: '终态恢复',
          createdAt: '2026-07-20T09:00:00Z',
          updatedAt: '2026-07-20T09:05:00Z',
        ),
        turns: const <AssistantTurnSummaryView>[
          AssistantTurnSummaryView(
            turnId: 'turn_cancelled',
            conversationId: conversationId,
            status: 'cancelled',
            inputText: '取消的问题',
            terminalSnapshot: AssistantRunTerminalSnapshotView(
              answerText: '',
              processes: [],
            ),
            createdAt: '2026-07-20T09:02:00Z',
            completedAt: '2026-07-20T09:02:30Z',
          ),
          AssistantTurnSummaryView(
            turnId: 'turn_failed',
            conversationId: conversationId,
            status: 'failed',
            inputText: '失败的问题',
            terminalSnapshot: AssistantRunTerminalSnapshotView(
              answerText: '',
              processes: [],
              failure: AssistantRunTerminalFailureView(
                code: 'ASSISTANT.SYSTEM.run_storage_unavailable',
                origin: 'system',
                kind: 'unavailable',
                nature: 'transient',
              ),
            ),
            createdAt: '2026-07-20T09:01:00Z',
            completedAt: '2026-07-20T09:01:30Z',
          ),
        ],
      ),
    );

    final snapshot = await loader.load(subAccountId: 'persona_assistant_uat');
    final assistantRows = snapshot!.transcript
        .whereType<AssistantAnswerTranscriptRow>()
        .toList(growable: false);

    expect(assistantRows.map((row) => row.content), <String>[
      AssistantText.assistantUnavailable,
      AssistantText.assistantTaskStatusCancelled,
    ]);
    expect(
      assistantRows.first.terminalSnapshot?.failure?.code,
      'ASSISTANT.SYSTEM.run_storage_unavailable',
    );
    expect(assistantRows.last.terminalSnapshot, isNotNull);
  });

  testWidgets('load_success：历史 snapshot 恢复后真实渲染到会话时间线', (tester) async {
    final loader = _RecordingHistoryLoader(
      snapshot: await _buildHistorySnapshot(),
    );
    final container = await _pumpDialogPage(
      tester,
      runFacet: _RecordingAssistantRunFacet(),
      historyLoader: loader,
    );

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(loader.loadCount, 1);
    expect(state.historyInitialized, isTrue);
    expect(state.historyLoading, isFalse);
    expect(state.transcript.map((row) => row.runtimeType), <Type>[
      UserTranscriptTimelineRow,
      AssistantAnswerTranscriptRow,
    ]);
    final restoredAnswer =
        state.transcript.last as AssistantAnswerTranscriptRow;
    expect(restoredAnswer.terminalSnapshot?.processes, hasLength(1));
    expect(
      restoredAnswer
          .terminalSnapshot
          ?.processes
          .single
          .acceptedReferences
          .single
          .title,
      '可信天气资料',
    );
    // 历史问答真实渲染上屏（非仅 provider 状态）。
    expect(
      find.textContaining(_historyQuestion, findRichText: true),
      findsWidgets,
    );
    expect(find.textContaining('深圳今天多云转晴', findRichText: true), findsWidgets);
    expect(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
      findsOneWidget,
    );

    await _disposeTree(tester);
  });

  testWidgets('empty_permission_error：历史 loader 抛 CloudException 时显示错误并可重试恢复', (
    tester,
  ) async {
    final loader = _RecordingHistoryLoader(
      error: CloudException(
        type: CloudErrorType.server,
        message: 'history storage unavailable',
        statusCode: AssistantErrorCode.runStorageUnavailable.httpStatus,
        code: AssistantErrorCode.runStorageUnavailable.code,
        userMessage: AssistantErrorCode.runStorageUnavailable.defaultMessage,
        runtimeFailure: testRuntimeFailure(
          code: AssistantErrorCode.runStorageUnavailable.code,
          kind: RuntimeFailureKind.unavailable,
        ),
      ),
    );
    final container = await _pumpDialogPage(
      tester,
      runFacet: _RecordingAssistantRunFacet(),
      historyLoader: loader,
    );

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(loader.loadCount, 1);
    expect(state.historyInitialized, isFalse);
    expect(state.historyLoading, isFalse);
    expect(state.retryAvailable, isTrue);
    expect(
      state.errorMessage,
      AssistantErrorCode.runStorageUnavailable.defaultMessage,
    );
    expect(state.transcript, isEmpty);
    expect(
      find.textContaining(_historyQuestion, findRichText: true),
      findsNothing,
    );
    // 页面不崩溃、不把失败伪装成无历史，结构化错误卡可见。
    expect(find.byType(PersonalAssistantConversationPage), findsOneWidget);
    expect(find.byType(AssistantConversationInlineError), findsOneWidget);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    loader
      ..error = null
      ..snapshot = await _buildHistorySnapshot();
    await container
        .read(personalAssistantStreamControllerProvider.notifier)
        .retryLastFailedAction();
    await tester.pump();

    final recovered = container.read(personalAssistantStreamControllerProvider);
    expect(loader.loadCount, 2);
    expect(recovered.historyInitialized, isTrue);
    expect(recovered.retryAvailable, isFalse);
    expect(recovered.errorMessage, isEmpty);
    expect(recovered.transcript, hasLength(2));
    expect(find.byType(AssistantConversationInlineError), findsNothing);

    await _disposeTree(tester);
  });

  testWidgets('primary_cta：历史恢复后继续发送新消息且历史行保留在前', (tester) async {
    const question = '那明天呢';
    const answer = '明天转晴，适合出行。';
    final loader = _RecordingHistoryLoader(
      snapshot: await _buildHistorySnapshot(),
    );
    final runFacet = _RecordingAssistantRunFacet(
      events: <AssistantStreamEventWire>[
        _event(seq: 1, eventType: AssistantStreamEventType.runStarted),
        _event(
          seq: 2,
          eventType: AssistantStreamEventType.completed,
          payload: const <String, dynamic>{'text': answer},
        ),
      ],
    );
    final container = await _pumpDialogPage(
      tester,
      runFacet: runFacet,
      historyLoader: loader,
    );

    await _sendUatText(tester, question);

    // 主 CTA 副作用：run 启动携带新问题；历史 loader 不重复加载。
    expect(runFacet.startedRunTexts, <String>[question]);
    expect(loader.loadCount, 1);

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(state.transcript.map((row) => row.runtimeType), <Type>[
      UserTranscriptTimelineRow,
      AssistantAnswerTranscriptRow,
      UserTranscriptTimelineRow,
      AssistantAnswerTranscriptRow,
    ]);
    expect(
      (state.transcript.first as UserTranscriptTimelineRow).content,
      _historyQuestion,
    );
    expect(
      (state.transcript.last as AssistantAnswerTranscriptRow).content,
      answer,
    );
    // 历史与新回答同屏：时间线同时渲染两代内容。
    expect(
      find.textContaining(_historyQuestion, findRichText: true),
      findsWidgets,
    );
    expect(find.textContaining('明天转晴', findRichText: true), findsWidgets);

    await _disposeTree(tester);
  });

  testWidgets('trace_context：页面曝光进入 VisitRecorder 且历史恢复后 turn 上下文推进', (
    tester,
  ) async {
    final recorder = _CapturingVisitRecorder();
    final runFacet = _RecordingAssistantRunFacet(
      events: <AssistantStreamEventWire>[
        _event(seq: 1, eventType: AssistantStreamEventType.runStarted),
        _event(
          seq: 2,
          eventType: AssistantStreamEventType.completed,
          payload: const <String, dynamic>{'text': '历史续聊回答'},
        ),
      ],
    );
    final container = await _pumpDialogPage(
      tester,
      runFacet: runFacet,
      historyLoader: _RecordingHistoryLoader(
        snapshot: await _buildHistorySnapshot(),
      ),
      visitRecorder: recorder,
    );

    // 历史承载页（对话页）曝光进入 VisitRecorder。
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page(PageNames.assistantPersonal).targetKey),
    );

    await _sendUatText(tester, '历史续聊问题');

    final state = container.read(personalAssistantStreamControllerProvider);
    // 云端历史恢复绑定 conversationId：续聊沿用已恢复会话，不新建云端会话
    // （R-ASSIST-001 收口后的会话生命周期语义）。
    expect(state.conversationId, 'restored_conversation_uat');
    expect(state.turnId, 'atn_uat_personal');
    expect(
      state.events.map((event) => event.eventType),
      containsAll(<AssistantStreamEventType>[
        AssistantStreamEventType.runStarted,
        AssistantStreamEventType.completed,
      ]),
    );

    await _disposeTree(tester);
  });
}

/// 由云端历史恢复真相源构造 snapshot：CloudAssistantHistoryLoader 消费
/// List conversations/turns 查询面（与 api_integration 的服务端断言同源）。
Future<AssistantHistorySnapshot> _buildHistorySnapshot() async {
  const conversationId = 'restored_conversation_uat';
  final loader = CloudAssistantHistoryLoader(
    _HistoryQueryFacetStub(
      conversation: AssistantConversationWire(
        conversationId: conversationId,
        userId: 'user_uat',
        summary: '深圳天气',
        createdAt: '2026-07-20T09:00:00Z',
        updatedAt: '2026-07-20T09:05:00Z',
      ),
      turns: const <AssistantTurnSummaryView>[
        AssistantTurnSummaryView(
          turnId: 'turn_restored_uat',
          conversationId: conversationId,
          status: 'completed',
          inputText: _historyQuestion,
          terminalSnapshot: AssistantRunTerminalSnapshotView(
            answerText: _historyAnswer,
            processes: [
              AssistantRunVisibleProcessView(
                processId: 'evidence-review:1',
                scope: 'skill',
                stage: 'evidence_review',
                status: 'completed',
                order: 4,
                summary: '已核对可信资料',
                skillId: 'weather',
                domainId: 'weather',
                searchedDocumentCount: 2,
                processedDocumentCount: 2,
                acceptedDocumentCount: 1,
                acceptedReferences: [
                  AssistantRunVisibleReferenceView(
                    title: '可信天气资料',
                    destination: CitationDestination(
                      kind: CitationDestinationKind.external,
                      url: 'https://example.com/weather',
                    ),
                    source: 'example.com',
                    snippet: '深圳天气公开摘要',
                  ),
                ],
              ),
            ],
          ),
          createdAt: '2026-07-20T09:00:00Z',
          completedAt: '2026-07-20T09:00:30Z',
        ),
      ],
    ),
  );
  final snapshot = await loader.load(subAccountId: 'persona_assistant_uat');
  return snapshot!;
}

/// 只服务历史恢复断言的最小查询桩。
class _HistoryQueryFacetStub extends _RecordingAssistantRunFacet {
  _HistoryQueryFacetStub({required this.conversation, required this.turns});

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

/// 统一 pump 真实对话页（assistantHistory 的真实承载页）。
Future<ProviderContainer> _pumpDialogPage(
  WidgetTester tester, {
  required _RecordingAssistantRunFacet runFacet,
  required AssistantHistoryLoader historyLoader,
  _CapturingVisitRecorder? visitRecorder,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantConversationRunFacetProvider.overrideWithValue(runFacet),
        assistantLearningAppendFacetProvider.overrideWithValue(
          _RecordingLearningAppendFacet(),
        ),
        appMessageQueryProvider.overrideWithValue(_FakeAppMessageQuery()),
        assistantHistoryLoaderProvider.overrideWithValue(historyLoader),
        activePersonaContextProvider.overrideWith(
          (ref) async => ActivePersonaContextViewData.fallback(
            subAccountId: 'persona_assistant_uat',
            ownerUserId: 'user_assistant_uat',
            displayName: '私助验收用户',
            avatarUrl: '',
          ),
        ),
        visitRecorderServiceProvider.overrideWithValue(
          visitRecorder ?? _CapturingVisitRecorder(),
        ),
        authSessionControllerProvider.overrideWith(
          _AuthenticatedSessionController.new,
        ),
      ],
      child: const MaterialApp(
        home: _AuthWarmup(child: PersonalAssistantConversationPage()),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 200));
  return ProviderScope.containerOf(
    tester.element(find.byType(PersonalAssistantConversationPage)),
  );
}

Future<void> _sendUatText(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(TestKeys.assistantChatInputField), text);
  await tester.pump();
  expect(find.byKey(TestKeys.assistantSendButton), findsOneWidget);
  await tester.tap(find.byKey(TestKeys.assistantSendButton));
  for (var i = 0; i < 12; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 50));
}

void _mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final directory = Directory.systemTemp.createTempSync(
    'qwq_assistant_history_uat_fs_',
  );
  tearDownAll(() {
    if (directory.existsSync()) {
      directory.deleteSync(recursive: true);
    }
  });
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}

AssistantStreamEventWire _event({
  required int seq,
  required AssistantStreamEventType eventType,
  Map<String, dynamic> payload = const <String, dynamic>{},
}) {
  final wirePayload = <String, dynamic>{...payload};
  if (eventType == AssistantStreamEventType.completed &&
      !wirePayload.containsKey('finalAnswer') &&
      wirePayload['text'] is String) {
    wirePayload['finalAnswer'] = wirePayload['text'];
  }
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
    eventId: 'evt_uat_$seq',
    conversationId: 'acv_uat_personal',
    turnId: 'atn_uat_personal',
    seq: seq,
    eventType: eventType,
    payload: wirePayload,
    createdAt: '2026-07-19T00:00:00Z',
  );
}

class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_assistant_uat',
    activeSubAccountId: 'persona_assistant_uat',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

/// Recording 历史 loader：记录加载次数；可返回 snapshot 或抛结构化异常。
class _RecordingHistoryLoader implements AssistantHistoryLoader {
  _RecordingHistoryLoader({this.snapshot, this.error});

  AssistantHistorySnapshot? snapshot;
  Object? error;
  int loadCount = 0;

  @override
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  }) async {
    loadCount += 1;
    final failure = error;
    if (failure != null) {
      throw failure;
    }
    return snapshot;
  }
}

/// Recording run Facet：记录 run 启动并回放固定事件流。
class _RecordingAssistantRunFacet implements AssistantConversationRunFacet {
  _RecordingAssistantRunFacet({
    this.events = const <AssistantStreamEventWire>[],
  });

  final List<AssistantStreamEventWire> events;
  final List<String> startedRunTexts = <String>[];
  final List<String> cancelledRunIds = <String>[];

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
    required String clientRequestId,
  }) async {
    return const AssistantConversationWire(
      conversationId: 'acv_uat_personal',
      userId: 'user_assistant_uat',
      createdAt: '2026-07-19T00:00:00Z',
      updatedAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantConversationListPage(
      items: <AssistantConversationWire>[],
    );
  }

  @override
  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) async {
    return AssistantConversationWire(
      conversationId: conversationId,
      userId: 'user_assistant_uat',
      createdAt: '2026-07-19T00:00:00Z',
      updatedAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantTurnListView(items: <AssistantTurnSummaryView>[]);
  }

  @override
  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    startedRunTexts.add(text);
    return AssistantTurnEnvelopeWire(
      turnId: 'atn_uat_personal',
      conversationId: conversationId,
      turnType: turnType,
      skillId: skillId,
      domainId: domainId,
      input: AssistantTurnInputWire(text: text),
      traceId: 'trace_uat_personal',
      createdAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    return AssistantTurnEnvelopeWire(
      turnId: runId,
      conversationId: 'acv_uat_personal',
      traceId: 'trace_uat_personal',
      createdAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({
    required String runId,
  }) async {
    cancelledRunIds.add(runId);
    return AssistantTurnEnvelopeWire(
      turnId: runId,
      conversationId: 'acv_uat_personal',
      status: 'cancelled',
      traceId: 'trace_uat_personal',
      createdAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
  }) {
    return Stream<AssistantStreamEventWire>.fromIterable(events);
  }
}

/// Recording 学习上报 Facet：turn 完成后补发待重试反馈事件时使用。
class _RecordingLearningAppendFacet implements AssistantLearningAppendFacet {
  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    return AssistantInteractionReportBatchAck(
      accepted: true,
      acceptedCount: events.length,
      count: events.length,
      resource: 'interaction_event_batch',
      mode: 'uat_recording',
    );
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    return AssistantScorecardReportBatchAck(
      accepted: true,
      count: scorecards.length,
      resource: 'scorecard_batch',
      mode: 'uat_recording',
    );
  }
}

/// turn 完成后 refreshManagementSummary 消费的未读数替身（避免 Remote 装配）。
class _FakeAppMessageQuery implements AppMessageQuery {
  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    return AppMessage(
      messageId: query.messageId,
      userId: 'user_assistant_uat',
      messageType: 'assistant',
      source: 'assistant_turn',
      sourceId: 'atn_uat_personal',
      destination: const AppMessageDestination(
        type: 'user',
        id: 'user_assistant_uat',
      ),
      title: '找私助提醒',
      summary: 'UAT 消息',
      target: const AppMessageTarget(
        targetType: 'assistant_turn',
        targetId: 'atn_uat_personal',
      ),
      read: false,
      createdAt: DateTime.utc(2026, 7, 19),
    );
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    return AppMessageUnreadCountSlice(unreadCount: 0);
  }

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    return AppMessageInboxSlice(items: const <AppMessage>[]);
  }
}

/// 捕获页面曝光的 VisitRecorder 替身（不触达 Hive/Remote）。
class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}

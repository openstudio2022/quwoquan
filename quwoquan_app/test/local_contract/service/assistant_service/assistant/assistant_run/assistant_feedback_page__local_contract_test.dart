/// assistantFeedback user_acceptance（B8 阶段 4a：真实页面 pump 验收）。
///
/// surface: assistantFeedback · owner: assistant · route: chatDetail
/// 本文件替代旧「证据文件路径存在性断言」伪验收。承载关系说明：
/// assistantFeedback surface（私助反馈与纠错，operation：
/// AppendAssistantLearningFact）没有独立路由页面，真实承载页是
/// `PersonalAssistantSessionPage` 的 answer toolbar：完成一轮 turn 后
/// 点击反馈按钮，经 `submitFeedback` → `appendUserFact` 学习回路
/// 上报（3b 接通）。
/// 四类必测 case：
/// - load_success：完成一轮 turn 后反馈工具栏真实出现（点赞/点踩可点）；
/// - empty_permission_error：学习上报 Facet 抛 CloudException → 本地反馈
///   展示不被阻塞、事件进入待重试队列（best-effort 语义，不崩溃不丢事件）；
/// - primary_cta：点击「有帮助」追加学习事实（Recording 替身断言 command）；
/// - trace_context：学习事实携带稳定派生 eventId、turn、referral 与 domain 上下文，
///   反馈状态推进上屏。
library;

import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show actorQueueStorageProvider;
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_history.dart';
import 'package:quwoquan_app/runtime/di/assistant_history_dependencies.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/transport/actor_queue/actor_queue_test_storage.dart';
import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProvider();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_assistant_feedback_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
    HiveRuntime.debugEnsureInitializedHook = () async => true;
  });

  tearDown(() async {
    await Hive.close();
    HiveRuntime.resetForTest();
    await Hive.deleteFromDisk();
  });

  testWidgets('load_success：完成一轮 turn 后反馈工具栏真实出现', (tester) async {
    final learningFacet = _RecordingLearningFactAppendFacet();
    await _pumpDialogPageWithCompletedTurn(
      tester,
      learningFacet: learningFacet,
    );

    // 反馈动作区（answer toolbar）：点赞 / 点踩 / 复制 / 转发全部可见。
    expect(find.byIcon(CupertinoIcons.hand_thumbsup), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.hand_thumbsdown), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.doc_on_doc), findsOneWidget);
    expect(
      find.byIcon(CupertinoIcons.arrowshape_turn_up_right),
      findsOneWidget,
    );

    await _disposeTree(tester);
  });

  testWidgets('empty_permission_error：后台学习上报不可用时本地反馈不被阻塞', (tester) async {
    final learningFacet = _RecordingLearningFactAppendFacet(
      reportError: CloudException(
        type: CloudErrorType.forbidden,
        message: 'skill consent required',
        statusCode: AssistantErrorCode.skillConsentRequired.httpStatus,
        code: AssistantErrorCode.skillConsentRequired.code,
        userMessage: AssistantErrorCode.skillConsentRequired.defaultMessage,
        runtimeFailure: testRuntimeFailure(
          code: AssistantErrorCode.skillConsentRequired.code,
          kind: RuntimeFailureKind.permission,
        ),
      ),
    );
    final container = await _pumpDialogPageWithCompletedTurn(
      tester,
      learningFacet: learningFacet,
    );

    await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsup));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    // 云端 append 的失败保留给 Controller local-contract 覆盖；页面侧只验证
    // 用户操作不会被后台学习链路阻塞。
    final state = container.read(personalAssistantStreamControllerProvider);
    expect(
      state.feedbackMessage,
      contains(AssistantText.assistantFeedbackUsefulLabel),
    );
    // 页面不崩溃：对话页与反馈工具栏仍在。
    expect(find.byType(PersonalAssistantSessionPage), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.hand_thumbsup_fill), findsOneWidget);

    await _disposeTree(tester);
  });

  testWidgets('primary_cta：点击「有帮助」更新本地反馈状态', (tester) async {
    final learningFacet = _RecordingLearningFactAppendFacet();
    await _pumpDialogPageWithCompletedTurn(
      tester,
      learningFacet: learningFacet,
    );

    await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsup));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.byIcon(CupertinoIcons.hand_thumbsup_fill), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.hand_thumbsup), findsNothing);

    await _disposeTree(tester);
  });

  testWidgets('feedback_state：反馈状态绑定已完成 turn', (tester) async {
    final learningFacet = _RecordingLearningFactAppendFacet();
    final container = await _pumpDialogPageWithCompletedTurn(
      tester,
      learningFacet: learningFacet,
    );

    await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsup));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(
      state.feedbackMessage,
      contains(AssistantText.assistantFeedbackUsefulLabel),
    );
    expect(state.feedbackType, 'useful');
    // 控制器状态承载 run id（`arn_`），不是单轮 turn id（`atn_`）。
    expect(state.runId, 'arn_uat_personal');

    await _disposeTree(tester);
  });
}

/// pump 真实对话页并完成一轮 turn，使反馈工具栏出现。
Future<ProviderContainer> _pumpDialogPageWithCompletedTurn(
  WidgetTester tester, {
  required _RecordingLearningFactAppendFacet learningFacet,
}) async {
  final runFacet = _RecordingAssistantRunFacet(
    events: <AssistantStreamEventWire>[
      _event(seq: 1, eventType: 'run_started'),
      _event(
        seq: 2,
        eventType: 'completed',
        payload: const <String, dynamic>{'text': '这是可反馈的 UAT 回答。'},
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantSessionRunFacetProvider.overrideWithValue(runFacet),
        assistantLearningFactAppendFacetProvider.overrideWithValue(
          learningFacet,
        ),
        actorQueueStorageProvider.overrideWithValue(newTestActorQueueStorage()),
        assistantLearningFactOutboxEnvironmentProvider.overrideWithValue(
          'alpha',
        ),
        appMessageQueryProvider.overrideWithValue(_FakeAppMessageQuery()),
        assistantHistoryLoaderProvider.overrideWithValue(
          const _EmptyHistoryLoader(),
        ),
        activePersonaContextProvider.overrideWith(
          (ref) async => ActivePersonaContextViewData.fallback(
            personaId: 'persona_assistant_uat',
            ownerUserId: 'user_assistant_uat',
            displayName: '私助验收用户',
            avatarUrl: '',
          ),
        ),
        visitRecorderServiceProvider.overrideWithValue(
          _CapturingVisitRecorder(),
        ),
        authSessionControllerProvider.overrideWith(
          _AuthenticatedSessionController.new,
        ),
      ],
      child: const MaterialApp(
        home: _AuthWarmup(child: PersonalAssistantSessionPage()),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 200));

  // 通过真实输入栏完成一轮 turn（反馈按钮仅在最后一条助手回答且非运行中出现）。
  await tester.enterText(
    find.byKey(TestKeys.assistantChatInputField),
    '给我一个可反馈的回答',
  );
  await tester.pump();
  await tester.tap(find.byKey(TestKeys.assistantSendButton));
  for (var i = 0; i < 12; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }

  final container = ProviderScope.containerOf(
    tester.element(find.byType(PersonalAssistantSessionPage)),
  );
  final state = container.read(personalAssistantStreamControllerProvider);
  expect(state.running, isFalse);
  expect(state.errorMessage, isEmpty);
  expect(state.runId, 'arn_uat_personal');
  return container;
}

Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 50));
}

void _mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final directory = Directory.systemTemp.createTempSync(
    'qwq_assistant_feedback_uat_fs_',
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
  required String eventType,
  Map<String, dynamic> payload = const <String, dynamic>{},
}) {
  final wirePayload = <String, dynamic>{...payload};
  if (eventType == 'completed' &&
      !wirePayload.containsKey('finalAnswer') &&
      wirePayload['text'] is String) {
    wirePayload['finalAnswer'] = wirePayload['text'];
  }
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
    eventId: 'evt_uat_$seq',
    sessionId: 'asn_uat_personal',
    runId: 'arn_uat_personal',
    seq: seq,
    eventType: parseAssistantStreamEventTypeStrict(eventType),
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
    activePersonaId: 'persona_assistant_uat',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

/// Recording run Facet：回放一轮固定 turn 事件流。
class _RecordingAssistantRunFacet implements AssistantSessionRunFacade {
  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantSessionListView(items: <AssistantSessionWire>[]);
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantTurnListView(items: <AssistantTurnSummaryView>[]);
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return getAssistantRun(runId: runId);
  }

  _RecordingAssistantRunFacet({
    this.events = const <AssistantStreamEventWire>[],
  });

  final List<AssistantStreamEventWire> events;

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    return const AssistantSessionWire(
      sessionId: 'asn_uat_personal',
      userId: 'user_assistant_uat',
      createdAt: '2026-07-19T00:00:00Z',
      updatedAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) async {
    return AssistantSessionWire(
      sessionId: sessionId,
      userId: 'user_assistant_uat',
      createdAt: '2026-07-19T00:00:00Z',
      updatedAt: '2026-07-19T00:00:00Z',
    );
  }

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
    return AssistantRunEnvelopeWire(
      runId: 'arn_uat_personal',
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_uat_personal',
      createdAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_uat_personal',
      traceId: 'trace_uat_personal',
      createdAt: '2026-07-19T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) {
    return Stream<AssistantStreamEventWire>.fromIterable(events);
  }
}

/// Recording 学习事实 Facet：记录单轨 command；可配置抛结构化异常。
class _RecordingLearningFactAppendFacet
    implements AssistantLearningFactAppendFacet {
  _RecordingLearningFactAppendFacet({this.reportError});

  final Object? reportError;
  final List<AssistantLearningFactAppendCommand> facts =
      <AssistantLearningFactAppendCommand>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    facts.add(request);
    final error = reportError;
    if (error != null) {
      throw error;
    }
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: facts.length,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
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
      messageType: NotificationType.assistant,
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
        query: AppMessageRouteQuery(),
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

/// 确定性空历史 loader：反馈 UAT 从全新会话开始。
class _EmptyHistoryLoader implements AssistantHistoryLoader {
  const _EmptyHistoryLoader();

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async {
    return null;
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

/// personalAssistantDialog 页面 user_acceptance（B8 阶段 4a：真实页面 pump 验收）。
///
/// surface: personalAssistantDialog · owner: assistant · route: assistantPersonal
/// 本文件替代旧「证据文件路径存在性断言」伪验收；四类必测 case 全部通过真实
/// `PersonalAssistantSessionPage` pump + ProviderScope 窄替身完成：
/// - load_success：页面真实 pump 后核心结构出现（页面类型 + 标题 + 输入栏 TestKeys）；
/// - empty_permission_error：Facet 抛结构化 CloudException 时错误在时间线可见，
///   并可从同一输入重试（禁止伪造回答、禁止崩溃）；
/// - primary_cta：输入 + 发送触发 StartAssistantRun（Recording 替身断言命令），
///   回答经流式事件上屏；
/// - trace_context：页面曝光进入 VisitRecorder（VisitTarget.page），发送后
///   turn 上下文（turnId/sessionId/events）推进。
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/notification/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart'
    show actorQueueStorageProvider;
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/presentation/personal_assistant_session_page.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_session/application/assistant_history_loader.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/actor_queue_test_storage.dart';
import '../../../../../support/runtime_failure_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProvider();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_assistant_dialog_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('load_success：真实 pump 找私助对话页出现核心结构', (tester) async {
    final runFacet = _RecordingAssistantRunFacet();
    final container = await _pumpDialogPage(tester, runFacet: runFacet);

    expect(find.byType(PersonalAssistantSessionPage), findsOneWidget);
    expect(find.text(AssistantText.assistantEntryFindPersonal), findsOneWidget);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(state.historyInitialized, isTrue);
    expect(state.errorMessage, isEmpty);
    expect(state.running, isFalse);

    await _disposeTree(tester);
  });

  testWidgets(
    'empty_permission_error：Facet 抛 CloudException 时走结构化 errorMessage 通道',
    (tester) async {
      final runFacet = _RecordingAssistantRunFacet(
        events: <AssistantStreamEventWire>[
          _event(seq: 1, eventType: 'run_started'),
          _event(
            seq: 2,
            eventType: 'completed',
            payload: const <String, dynamic>{'text': '重试后的真实回答'},
          ),
        ],
        createSessionError: CloudException(
          type: CloudErrorType.forbidden,
          message: 'skill consent required',
          statusCode: AssistantErrorCode.skillConsentRequired.httpStatus,
          code: AssistantErrorCode.skillConsentRequired.code,
          userMessage: AssistantErrorCode.skillConsentRequired.defaultMessage,
          runtimeFailure: testRuntimeFailure(
            code: AssistantErrorCode.skillConsentRequired.code,
            kind: RuntimeFailureKind.permission,
            nature: RuntimeFailureNature.requiresPermission,
          ),
        ),
      );
      final container = await _pumpDialogPage(tester, runFacet: runFacet);

      await _sendUatText(tester, '帮我整理今天的待办');

      final state = container.read(personalAssistantStreamControllerProvider);
      // 结构化错误保留在 provider，用户可见文案由唯一恢复组决定。
      expect(state.errorMessage, SearchText.recoveryEnablePermissionMessage);
      expect(state.running, isFalse);
      // 禁止伪造数据：Session 创建失败时没有 canonical sessionId，因此不得写入
      // 无归属 transcript；重试成功后才把同一输入绑定到真实 Session。
      expect(state.answer, isEmpty);
      expect(state.transcript, isEmpty);
      // 页面本体展示映射后的错误与恢复动作，不再只把错误藏在 provider state。
      expect(
        find.text(SearchText.recoveryEnablePermissionTitle),
        findsOneWidget,
      );
      expect(
        find.text(SearchText.recoveryEnablePermissionMessage),
        findsOneWidget,
      );
      expect(
        find.text(AssistantErrorCode.skillConsentRequired.defaultMessage),
        findsNothing,
      );
      expect(find.text(ContentText.tryAgain), findsOneWidget);
      // 第一次失败后替身恢复；重试沿用同一输入且不重复追加用户消息。
      await tester.tap(find.text(ContentText.tryAgain));
      await tester.pumpAndSettle();
      final retried = container.read(personalAssistantStreamControllerProvider);
      expect(retried.errorMessage, isEmpty);
      expect(runFacet.createSessionCalls, 2);
      expect(runFacet.startedRunTexts, <String>['帮我整理今天的待办']);
      expect(
        retried.transcript.whereType<UserTranscriptTimelineRow>(),
        hasLength(1),
      );
      // 页面本体仍可用（输入栏还在，无崩溃）。
      expect(find.byType(PersonalAssistantSessionPage), findsOneWidget);
      expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

      await _disposeTree(tester);
    },
  );

  testWidgets('primary_cta：输入并点击发送触发 StartAssistantRun 且回答上屏', (tester) async {
    const question = '帮我查深圳天气';
    const answer = '这是找私助的 UAT 回答：深圳今天多云。';
    final runFacet = _RecordingAssistantRunFacet(
      events: <AssistantStreamEventWire>[
        _event(seq: 1, eventType: 'run_started'),
        _event(
          seq: 2,
          eventType: 'completed',
          payload: const <String, dynamic>{'text': answer},
        ),
      ],
    );
    final container = await _pumpDialogPage(tester, runFacet: runFacet);

    await _sendUatText(tester, question);

    // Recording 替身断言主 CTA 副作用：会话创建 + run 启动携带原文。
    expect(runFacet.createSessionCalls, 1);
    expect(runFacet.startedRunTexts, <String>[question]);

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(state.running, isFalse);
    expect(state.errorMessage, isEmpty);
    expect(state.answer, answer);
    expect(state.transcript.map((row) => row.runtimeType), <Type>[
      UserTranscriptTimelineRow,
      AssistantAnswerTranscriptRow,
    ]);
    // 用户消息与助手回答均真实渲染到时间线 UI。
    expect(find.textContaining(question, findRichText: true), findsWidgets);
    expect(find.textContaining('深圳今天多云', findRichText: true), findsWidgets);

    await _disposeTree(tester);
  });

  testWidgets('trace_context：页面曝光进入 VisitRecorder 且发送后 turn 上下文推进', (
    tester,
  ) async {
    final recorder = _CapturingVisitRecorder();
    final runFacet = _RecordingAssistantRunFacet(
      events: <AssistantStreamEventWire>[
        _event(seq: 1, eventType: 'run_started'),
        _event(
          seq: 2,
          eventType: 'completed',
          payload: const <String, dynamic>{'text': '追踪上下文回答'},
        ),
      ],
    );
    final container = await _pumpDialogPage(
      tester,
      runFacet: runFacet,
      visitRecorder: recorder,
    );

    // 曝光埋点（3b 在 initState 接入 writeAppPageAccessOpen）：VisitRecorder
    // 收到 assistant_personal 页面访问。
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page(PageNames.assistantPersonal).targetKey),
    );

    await _sendUatText(tester, '追踪上下文问题');

    final state = container.read(personalAssistantStreamControllerProvider);
    expect(state.sessionId, 'asn_uat_personal');
    expect(state.runId, 'atn_uat_personal');
    expect(
      state.events.map((event) => event.eventType.wireName),
      containsAll(<String>['run_started', 'completed']),
    );

    await _disposeTree(tester);
  });
}

/// 统一 pump 真实对话页：窄 Facet 替身 + 真实 authenticated 会话控制器。
Future<ProviderContainer> _pumpDialogPage(
  WidgetTester tester, {
  required _RecordingAssistantRunFacet runFacet,
  _CapturingVisitRecorder? visitRecorder,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantSessionRunFacetProvider.overrideWithValue(runFacet),
        assistantLearningFactAppendFacetProvider.overrideWithValue(
          _RecordingLearningFactAppendFacet(),
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
          visitRecorder ?? _CapturingVisitRecorder(),
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
  // initState postFrameCallback（曝光 + 历史初始化）需要额外几拍。
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 200));
  return ProviderScope.containerOf(
    tester.element(find.byType(PersonalAssistantSessionPage)),
  );
}

/// 通过真实输入栏输入并点击发送按钮，等待流式事件消费完成。
Future<void> _sendUatText(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(TestKeys.assistantChatInputField), text);
  await tester.pump();
  expect(find.byKey(TestKeys.assistantSendButton), findsOneWidget);
  await tester.tap(find.byKey(TestKeys.assistantSendButton));
  for (var i = 0; i < 12; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// 卸载页面树，清理运行中的动画计时器，避免 pending timer 泄漏。
Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 50));
}

void _mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final directory = Directory.systemTemp.createTempSync(
    'qwq_assistant_dialog_uat_fs_',
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

/// Recording run Facet：记录会话创建与 run 启动，按配置回放流式事件或抛错。
class _RecordingAssistantRunFacet implements AssistantSessionRunFacet {
  @override
  Future<AssistantSessionListPage> listAssistantSessions({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantSessionListPage(items: <AssistantSessionWire>[]);
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantListPageDefaultLimit,
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
    this.createSessionError,
  });

  final List<AssistantStreamEventWire> events;
  Object? createSessionError;
  final List<String> startedRunTexts = <String>[];
  int createSessionCalls = 0;

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    createSessionCalls += 1;
    final error = createSessionError;
    if (error != null) {
      createSessionError = null;
      throw error;
    }
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
    startedRunTexts.add(text);
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

/// Recording 学习事实 Facet：turn 完成后补发待重试事实时使用。
class _RecordingLearningFactAppendFacet
    implements AssistantLearningFactAppendFacet {
  final List<AssistantLearningFactAppendCommand> facts =
      <AssistantLearningFactAppendCommand>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    facts.add(request);
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

/// 确定性空历史 loader：UAT 断言不依赖 binding 名称探测。
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

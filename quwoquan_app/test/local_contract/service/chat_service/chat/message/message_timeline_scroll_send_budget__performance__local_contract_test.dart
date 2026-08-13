// 长会话打开首帧、滚动与发送确认的性能预算契约（固定 seed 千条消息 + 运行时采样）。
//
// 预算数值唯一声明于 test/support/runtime/performance/performance_budget_probe.dart
// 的 MessageRuntimePerformanceBudgets；本测试不承载第二份预算值。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-002.t3
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_conversation_page.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'package:quwoquan_app/runtime/observability/trackers/chat_conversation_performance_observability.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/runtime/performance/performance_budget_probe.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/message/message_timeline_cache_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

const _conversationId = 'fixture_conv_direct';
const _currentUserId = 'fixture_user_current';
const _seededMessageCount = 1000;
const _scrollSampleCount = 24;

/// 固定 seed 的千条量级消息：内容、seq 与时间戳全部确定性生成。
Map<String, List<Map<String, dynamic>>> _longConversationMessages() {
  return <String, List<Map<String, dynamic>>>{
    _conversationId: <Map<String, dynamic>>[
      for (var seq = 1; seq <= _seededMessageCount; seq++)
        <String, dynamic>{
          'id': 'fixture_msg_perf_$seq',
          'conversationId': _conversationId,
          'senderId': seq.isEven ? _currentUserId : 'fixture_user_friend',
          'type': 'text',
          'content': '长会话预算样本消息 $seq',
          'seq': seq,
          'status': 'sent',
          'timestamp': '2026-06-10T10:00:00Z',
        },
    ],
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_perf_budget_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('千条量级会话的打开首帧、滚动与发送确认在声明预算内', (tester) async {
    // —— 首帧预算：pumpWidget → 首条消息可见的 wall time。 ——
    final telemetry = RecordingAppTelemetryRecorder();
    final openProbe = PerformanceBudgetProbe();
    await openProbe.measure(() async {
      await tester.pumpWidget(_buildConversationApp(telemetry: telemetry));
      var firstMessageVisible = false;
      for (var i = 0; i < 60 && !firstMessageVisible; i++) {
        await tester.pump(const Duration(milliseconds: 50));
        firstMessageVisible = find
            .textContaining('长会话预算样本消息')
            .evaluate()
            .isNotEmpty;
      }
      expect(
        firstMessageVisible,
        isTrue,
        reason: '打开会话必须渲染出首条可见消息',
      );
    });
    expectWithinBudgetMs(
      label: '打开会话到首条消息可见',
      actualMs: openProbe.medianMs,
      budgetMs: MessageRuntimePerformanceBudgets.openToFirstMessageFrameBudgetMs,
    );
    await tester.pump(const Duration(milliseconds: 350));
    expect(find.byType(ChatConversationPage), findsOneWidget);

    // —— 首屏可用采样：真实页面接线恰好上报一次。 ——
    final firstScreenSamples = telemetry.recorded
        .where(
          (event) =>
              event.extensions['operationId'] ==
              ChatConversationPerformanceMetricNames.firstScreenTtiMs,
        )
        .toList();
    expect(
      firstScreenSamples,
      hasLength(1),
      reason: '打开会话到首屏可用必须恰好上报一次性能采样',
    );
    expect(firstScreenSamples.first.eventType, 'performance_sample');

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('千条量级会话的滚动与发送确认在声明预算内', (tester) async {
    await tester.pumpWidget(_buildConversationApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(find.byType(ChatConversationPage), findsOneWidget);

    // —— 滚动预算：重复采样单次滚动交互（手势 + 一帧）wall time。 ——
    final scrollProbe = PerformanceBudgetProbe();
    final scrollable = find.byType(Scrollable).first;
    // 预热一帧，排除首次布局成本混入滚动样本。
    await tester.drag(scrollable, const Offset(0, 160));
    await tester.pump();
    for (var i = 0; i < _scrollSampleCount; i++) {
      final direction = i.isEven ? 160.0 : -160.0;
      await scrollProbe.measure(() async {
        await tester.drag(scrollable, Offset(0, direction));
        await tester.pump();
      });
    }
    expectWithinBudgetMs(
      label: '长会话滚动中位帧',
      actualMs: scrollProbe.medianMs,
      budgetMs: MessageRuntimePerformanceBudgets.scrollMedianPumpBudgetMs,
    );
    expectWithinRatioBudget(
      label: '长会话滚动 jank 比',
      actualRatio: scrollProbe.jankRatio(
        MessageRuntimePerformanceBudgets.scrollJankFrameThresholdMs,
      ),
      budgetRatio: MessageRuntimePerformanceBudgets.scrollJankRatioBudget,
    );

    // —— 发送确认预算：输入 → 主 CTA → 时间线出现该消息的 wall time。 ——
    final container = ProviderScope.containerOf(
      tester.element(find.byType(ChatConversationPage)),
    );
    const marker = '性能预算发送确认样本';
    final sendProbe = PerformanceBudgetProbe();
    await sendProbe.measure(() async {
      await tester.enterText(find.byKey(TestKeys.chatInputTextField), marker);
      await tester.pump();
      await tester.tap(find.byKey(TestKeys.chatInputSendButton));
      var confirmed = false;
      for (var i = 0; i < 40 && !confirmed; i++) {
        await tester.pump(const Duration(milliseconds: 50));
        confirmed = container
            .read(chatMessageTimelineProvider(_conversationId))
            .messages
            .any((message) => message.content == marker);
      }
      expect(confirmed, isTrue, reason: '发送的消息必须出现在时间线中');
    });
    expectWithinBudgetMs(
      label: '发送到气泡确认',
      actualMs: sendProbe.medianMs,
      budgetMs: MessageRuntimePerformanceBudgets.sendConfirmBudgetMs,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

/// 千条 seed 会话页的统一装配：首帧与滚动/发送两个用例共用同一形态。
Widget _buildConversationApp({RecordingAppTelemetryRecorder? telemetry}) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      if (telemetry != null)
        appTelemetryReporterProvider.overrideWithValue(telemetry),
      ...chatTestRepositoryOverrides(seedMessages: _longConversationMessages()),
      chatMessageCommandWriterProvider.overrideWithValue(
        _ImmediateAckMessageWriter(),
      ),
      chatMessageTimelineCacheProvider.overrideWithValue(
        const EmptyChatMessageTimelineCache(),
      ),
      contentConfigRepositoryProvider.overrideWithValue(
        InMemoryContentConfigRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _MutualRelationshipCapability(),
      ),
      realtimeConnectionManagerProvider.overrideWith(
        _NoopRealtimeConnectionNotifier.new,
      ),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData(
          personaId: 'persona_chat_perf',
          ownerUserId: _currentUserId,
          subjectType: 'persona',
          displayName: '性能预算用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
      authSessionControllerProvider.overrideWith(
        _AuthenticatedSessionController.new,
      ),
    ],
    child: MaterialApp(
      navigatorObservers: <NavigatorObserver>[chatRouteObserver],
      home: _AuthWarmup(
        child: ChatConversationPage(conversationId: _conversationId, onBack: _noop),
      ),
    ),
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
    ownerId: _currentUserId,
    activePersonaId: 'persona_chat_perf',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

class _ImmediateAckMessageWriter implements ChatMessageCommandWriter {
  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    return ChatSendMessageResult(
      messageId: 'message_${command.clientMsgId}',
      seq: _seededMessageCount + 1,
      timestamp: DateTime.utc(2026, 7, 15),
    );
  }
}

class _NoopRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
  _NoopRealtimeConnectionNotifier()
    : super(
        delegateFactory:
            ({
              required ref,
              required onStateChanged,
              required currentUserIdResolver,
            }) => throw StateError('overridden build must not create delegate'),
      );

  @override
  TransportState build() => TransportState.idle;

  @override
  void onAppForeground() {}

  @override
  void onAppBackground() {}

  @override
  void onEnterConversation(String conversationId) {}

  @override
  void onLeaveConversation() {}
}

class _MutualRelationshipCapability extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return RelationshipCapabilityViewData(
      viewerPersonaId: 'persona_chat_perf',
      targetPersonaId: targetUserId,
      relationState: 'mutual',
      canFollow: false,
      canUnfollow: true,
      canFollowBack: false,
      canGreet: false,
      canCreateDirectConversation: true,
      canSendMessage: true,
      canOpenConversation: true,
      hasPendingGreeting: false,
      hasFormalConversation: true,
      canStartVoiceCall: true,
      canStartVideoCall: true,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

void _noop() {}

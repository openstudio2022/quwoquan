// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-004
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003
//
// 群邀完整 UI journey 契约（收口 call-experience OPEN-001）：
// 通话页控制条邀请入口 → 参与者 picker 勾选 → 确认提交 InviteToCall →
// 聚合会话与 roster 同步新增成员，单条 journey 全链路可达。
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participants_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_timer_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_participant_picker_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/voice_call_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble seed：音频通话。
const String _seedAudioCallId = '11111111-1111-4111-8111-111111111111';

final class _JourneyContactRepository implements ChatContactRepository {
  _JourneyContactRepository(this._delegate);

  final ChatContactRepository _delegate;

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return CursorPage<ChatContactRowViewData>(
      items: [
        ChatContactRowViewData(
          userId: 'user-invitee-1',
          userHandle: 'user-invitee-1',
          displayName: '待邀请联系人',
          avatarUrl: '',
          bio: '',
          metFrom: '',
          lastInteraction: '',
          relationState: 'mutual',
          isStarred: false,
        ),
      ],
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) {
    return _delegate.noSuchMethod(invocation);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('群邀 journey：控制条入口 → picker 勾选 → InviteToCall → roster 同步', (
    tester,
  ) async {
    final callSessions = CallSessionTypedDouble();
    await callSessions.answerCall(RtcCallIdCommand(callId: _seedAudioCallId));
    final facets = ChatTestFacets();
    final container = ProviderContainer(
      overrides: [
        rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
        rtcCallQueryProvider.overrideWith((ref, surface) => callSessions),
        rtcCallLifecycleCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallParticipantCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallMediaControlWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        ...chatTestRepositoryOverrides(
          facets: facets,
          contact: _JourneyContactRepository(facets.contact),
        ),
      ],
    );
    addTearDown(container.dispose);

    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) =>
              const VoiceCallPage(callId: _seedAudioCallId),
        ),
        GoRoute(
          path: AppRoutePaths.rtcPickParticipants,
          builder: (context, state) => CallParticipantPickerPage(
            routeExtra: CallParticipantPickerRouteExtra.fromRouter(
              state.extra,
            ),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    container
        .read(callSessionProvider.notifier)
        .loadFromSession(
          await callSessions.getCall(RtcGetCallQuery(callId: _seedAudioCallId)),
        );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();

    // 1. 控制条邀请入口。
    expect(find.text(CallText.callInvite), findsOneWidget);
    await tester.tap(find.text(CallText.callInvite));
    await tester.pumpAndSettle();

    // 2. picker 展示可邀请联系人并勾选。
    expect(find.byType(CallParticipantPickerPage), findsOneWidget);
    expect(find.text('待邀请联系人'), findsOneWidget);
    await tester.tap(find.text('待邀请联系人'));
    await tester.pump();

    // 3. 确认提交 InviteToCall 并返回通话页。
    await tester.tap(find.text(UITextConstants.callConfirmSelected(1)));
    await tester.pumpAndSettle();
    expect(find.byType(CallParticipantPickerPage), findsNothing);

    // 4. 聚合会话与 roster 同步新增成员。
    await tester.pump();
    final session = container.read(callSessionProvider).session!;
    expect(
      session.participants!.map((p) => p.userId),
      contains('user-invitee-1'),
      reason: 'InviteToCall 必须真实提交并写回聚合会话',
    );
    expect(
      container
          .read(callParticipantsProvider)
          .participants
          .map((p) => p.userId),
      contains('user-invitee-1'),
      reason: 'roster 必须随邀请结果同步',
    );

    // 清理：卸载页面、停掉通话页启动的周期计时器并消化 auto-hide 计时器。
    await tester.pumpWidget(const SizedBox.shrink());
    container.read(callTimerProvider.notifier).reset();
    await tester.pump(const Duration(seconds: 8));
  });
}

final class _NoopRtcRoomService extends RtcRoomService {
  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}

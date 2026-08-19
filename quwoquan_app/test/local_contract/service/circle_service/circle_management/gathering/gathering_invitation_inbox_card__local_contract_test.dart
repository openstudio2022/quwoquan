// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-006
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_invitation_inbox_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AppMessage,
        AppMessageDestination,
        AppMessageGatheringInvitation,
        AppMessageGatheringInvitationAction,
        AppMessageGatheringInvitationActionIntent,
        AppMessageGatheringInvitationPlace,
        AppMessageGatheringInvitationSchedule,
        AppMessageGatheringInvitationStatus,
        AppMessageRouteQuery,
        AppMessageTarget,
        NotificationType;

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

// 通知收件箱 Gathering 邀请专卡契约（1对1 邀约闭环的接收侧）：
// - pending 邀请渲染披露安全快照与 accept/decline 双动作；
// - 动作只携带消息 action intent 的 owner versions 打 Circle typed op；
// - accept 成功进入行动详情；decline 成功给「已婉拒」反馈；
// - 动作失败不半持久化、不 crash，收件箱仍可重试。

AppMessage _invitationMessage({
  AppMessageGatheringInvitationStatus status =
      AppMessageGatheringInvitationStatus.pending,
  List<AppMessageGatheringInvitationActionIntent>? intents,
}) {
  return AppMessage(
    messageId: 'msg-invite-1',
    userId: 'user-1',
    messageType: NotificationType.circle,
    source: 'circle',
    sourceId: 'gathering-duo-1',
    destination: const AppMessageDestination(type: 'inbox', id: 'user-1'),
    title: '邀你同行',
    summary: '周六下午 · 森林公园',
    target: const AppMessageTarget(
      targetType: 'gathering',
      targetId: 'gathering-duo-1',
      query: AppMessageRouteQuery(),
    ),
    gatheringInvitation: AppMessageGatheringInvitation(
      gatheringId: 'gathering-duo-1',
      inviterPersonaId: 'persona-inviter',
      recipientPersonaId: 'persona-recipient',
      purposeSummary: '去森林公园走走',
      schedule: const AppMessageGatheringInvitationSchedule(
        timezone: 'Asia/Shanghai',
        dateLabel: '周六下午',
      ),
      place: const AppMessageGatheringInvitationPlace(
        mode: 'physical',
        coarsePlaceLabel: '森林公园',
      ),
      participationVersion: 1,
      status: status,
      actionIntents:
          intents ??
          const <AppMessageGatheringInvitationActionIntent>[
            AppMessageGatheringInvitationActionIntent(
              action: AppMessageGatheringInvitationAction.accept,
              expectedGatheringVersion: 7,
              expectedParticipationVersion: 1,
            ),
            AppMessageGatheringInvitationActionIntent(
              action: AppMessageGatheringInvitationAction.decline,
              expectedGatheringVersion: 7,
              expectedParticipationVersion: 1,
            ),
          ],
    ),
    read: false,
    createdAt: DateTime.utc(2026, 8, 12, 10),
  );
}

class _ResolveCounter {
  int calls = 0;
}

Future<void> _pumpCard(
  WidgetTester tester, {
  required InMemoryGatheringPort port,
  required AppMessage message,
  required _ResolveCounter resolved,
  List<String> pushedPaths = const <String>[],
}) async {
  final paths = List<String>.of(pushedPaths);
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (context, state) => Scaffold(
          body: GatheringInvitationInboxCard(
            message: message,
            invitation: message.gatheringInvitation!,
            onResolved: () async => resolved.calls += 1,
            fgPrimary: const Color(0xFF111111),
            fgSecondary: const Color(0xFF666666),
            backgroundColor: const Color(0xFFFFFFFF),
          ),
        ),
      ),
      GoRoute(
        path: '/gatherings/:id',
        builder: (context, state) {
          paths.add(state.uri.path);
          return const SizedBox.shrink();
        },
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: gatheringBoundaryOverrides(port),
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('pending 邀请渲染披露安全快照与双动作', (tester) async {
    final port = InMemoryGatheringPort();
    await _pumpCard(
      tester,
      port: port,
      message: _invitationMessage(),
      resolved: _ResolveCounter(),
    );

    expect(
      find.textContaining(GatheringText.invitationCardTitlePrefix),
      findsOneWidget,
    );
    expect(find.text('周六下午 · 森林公园'), findsOneWidget);
    expect(
      find.byKey(GatheringInvitationInboxCard.acceptKeyFor('msg-invite-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(GatheringInvitationInboxCard.declineKeyFor('msg-invite-1')),
      findsOneWidget,
    );
  });

  testWidgets('accept 携带 intent versions 打 Circle 并进入行动详情', (tester) async {
    final port = InMemoryGatheringPort();
    final resolved = _ResolveCounter();
    await _pumpCard(
      tester,
      port: port,
      message: _invitationMessage(),
      resolved: resolved,
    );

    await tester.tap(
      find.byKey(GatheringInvitationInboxCard.acceptKeyFor('msg-invite-1')),
    );
    await tester.pumpAndSettle();

    expect(port.acceptCalls, 1);
    expect(resolved.calls, 1);
    // 已跳转进详情路由（原卡片不再在树上）。
    expect(
      find.byKey(
        const ValueKey<String>('gathering-invitation-card-msg-invite-1'),
      ),
      findsNothing,
    );
  });

  testWidgets('decline 打 Circle typed op 并给已婉拒反馈', (tester) async {
    final port = InMemoryGatheringPort();
    final resolved = _ResolveCounter();
    await _pumpCard(
      tester,
      port: port,
      message: _invitationMessage(),
      resolved: resolved,
    );

    await tester.tap(
      find.byKey(GatheringInvitationInboxCard.declineKeyFor('msg-invite-1')),
    );
    await tester.pumpAndSettle();

    expect(port.declineCalls, 1);
    expect(port.lastDecline?.gatheringId, 'gathering-duo-1');
    expect(port.lastDecline?.expectedGatheringVersion, 7);
    expect(port.lastDecline?.expectedParticipationVersion, 1);
    expect(resolved.calls, 1);
    expect(find.text(GatheringText.invitationDeclinedFeedback), findsOneWidget);
    // 排空 toast 自动消失 timer，避免测试结束时仍有 pending timer。
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('decline 失败不半持久化：报错提示且收件箱不收口', (tester) async {
    final port = InMemoryGatheringPort()
      ..declineError = StateError('version conflict');
    final resolved = _ResolveCounter();
    await _pumpCard(
      tester,
      port: port,
      message: _invitationMessage(),
      resolved: resolved,
    );

    await tester.tap(
      find.byKey(GatheringInvitationInboxCard.declineKeyFor('msg-invite-1')),
    );
    await tester.pumpAndSettle();

    expect(port.declineCalls, 1);
    expect(resolved.calls, 0);
    expect(
      find.text(GatheringText.invitationActionFailedToast),
      findsOneWidget,
    );
    // 双动作仍在，可重试。
    expect(
      find.byKey(GatheringInvitationInboxCard.acceptKeyFor('msg-invite-1')),
      findsOneWidget,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('非 pending 状态不渲染动作按钮', (tester) async {
    final port = InMemoryGatheringPort();
    await _pumpCard(
      tester,
      port: port,
      message: _invitationMessage(
        status: AppMessageGatheringInvitationStatus.declined,
      ),
      resolved: _ResolveCounter(),
    );

    expect(
      find.byKey(GatheringInvitationInboxCard.acceptKeyFor('msg-invite-1')),
      findsNothing,
    );
    expect(
      find.byKey(GatheringInvitationInboxCard.declineKeyFor('msg-invite-1')),
      findsNothing,
    );
  });
}

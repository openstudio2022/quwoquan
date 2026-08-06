// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/presentation/circle_group_membership_panel.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('legal absence shows explicit apply and typed pending terminal', (
    tester,
  ) async {
    final commands = _PanelCommands();
    await tester.pumpWidget(
      _app(queries: const _PanelQueries(membership: null), commands: commands),
    );
    await tester.pumpAndSettle();

    expect(find.text(CommunityText.circleGroupMembershipNotJoined), findsOne);
    await tester.tap(
      find.byKey(const ValueKey<String>('circle-group-membership-apply')),
    );
    await tester.pumpAndSettle();

    expect(commands.applyCalls, 1);
    expect(find.text(CommunityText.circleGroupMembershipPending), findsOne);
  });

  testWidgets('active membership exposes explicit leave and keeps left state', (
    tester,
  ) async {
    final commands = _PanelCommands();
    await tester.pumpWidget(
      _app(
        queries: _PanelQueries(
          membership: _membership(CircleGroupMembershipState.active),
        ),
        commands: commands,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(CommunityText.circleGroupMembershipActive), findsOne);
    await tester.tap(
      find.byKey(const ValueKey<String>('circle-group-membership-leave')),
    );
    await tester.pumpAndSettle();

    expect(commands.leaveCalls, 1);
    expect(find.text(CommunityText.circleGroupMembershipLeft), findsOne);
  });
}

Widget _app({
  required CircleGroupMembershipQueries queries,
  required CircleGroupMembershipCommands commands,
}) => CupertinoApp(
  home: CupertinoPageScaffold(
    child: CircleGroupMembershipPanel(
      circleId: 'circle-1',
      group: _group,
      access: CircleGroupMembershipAccess(
        commands: commands,
        queries: queries,
        isAbsent: (error) => error is _PanelMissing,
      ),
      isDark: false,
    ),
  ),
);

final CircleGroupSlice _group = CircleGroupSlice(
  groupId: 'group-1',
  version: 1,
  circleId: 'circle-1',
  parentGroupId: null,
  groupType: CircleGroupType.publicGroup,
  nodeType: null,
  name: '默认公共群',
  description: '',
  visibility: CircleGroupVisibility.public,
  joinPolicy: CircleGroupJoinPolicy.applyOnly,
  conversationId: 'conversation-1',
  storageEnabled: true,
  noticeEnabled: true,
  isDefaultPublicGroup: true,
  status: CircleGroupStatus.active,
  memberCount: 1,
  createdAt: DateTime.utc(2026, 8, 5),
  updatedAt: DateTime.utc(2026, 8, 6),
);

CircleGroupMembershipSlice _membership(CircleGroupMembershipState state) =>
    CircleGroupMembershipSlice(
      membershipId: 'membership-1',
      version: 1,
      groupId: 'group-1',
      circleId: 'circle-1',
      personaId: 'persona-1',
      role: CircleGroupMembershipRole.member,
      state: state,
      joinedAt: state == CircleGroupMembershipState.active
          ? DateTime.utc(2026, 8, 6)
          : null,
      leftAt: state == CircleGroupMembershipState.left
          ? DateTime.utc(2026, 8, 6)
          : null,
      decidedAt: null,
      createdAt: DateTime.utc(2026, 8, 5),
      updatedAt: DateTime.utc(2026, 8, 6),
    );

final class _PanelQueries implements CircleGroupMembershipQueries {
  const _PanelQueries({required this.membership});

  final CircleGroupMembershipSlice? membership;

  @override
  Future<CircleGroupMembershipSlice> getMy(
    MyCircleGroupMembershipQuery query,
  ) async {
    final value = membership;
    if (value == null) throw const _PanelMissing();
    return value;
  }

  @override
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  ) async => CircleGroupMembershipPageSlice(
    items: <CircleGroupMembershipSlice>[],
  );
}

final class _PanelCommands implements CircleGroupMembershipCommands {
  int applyCalls = 0;
  int leaveCalls = 0;

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) async {
    applyCalls++;
    return _result(CircleGroupMembershipState.pending);
  }

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) async {
    leaveCalls++;
    return _result(CircleGroupMembershipState.left);
  }

  @override
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  ) => throw UnsupportedError('approve');

  @override
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  ) => throw UnsupportedError('reject');

  @override
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  ) => throw UnsupportedError('remove');

  @override
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  ) => throw UnsupportedError('updateRole');
}

CircleGroupMembershipCommandResult _result(CircleGroupMembershipState state) =>
    CircleGroupMembershipCommandResult(
      membershipId: 'membership-1',
      version: 2,
      role: CircleGroupMembershipRole.member,
      state: state,
      idempotentReplay: false,
    );

final class _PanelMissing implements Exception {
  const _PanelMissing();
}

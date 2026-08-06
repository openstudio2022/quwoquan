// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_flow.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('canonical not-found is a legal not-joined state', () async {
    final states = <CircleGroupMembershipViewState>[];
    final flow = _flow(
      queries: _MembershipQueries(
        getMyHandler: (_) async => throw const _MembershipMissing(),
      ),
      commands: _MembershipCommands(),
      states: states,
    );

    await flow.load();

    expect(states.map((state) => state.status), <Object?>[
      CircleGroupMembershipViewStatus.loading,
      CircleGroupMembershipViewStatus.notJoined,
    ]);
    expect(flow.state.error, isNull);
  });

  test('pending and active slices remain distinct typed states', () async {
    for (final wireState in <CircleGroupMembershipState>[
      CircleGroupMembershipState.pending,
      CircleGroupMembershipState.active,
    ]) {
      final flow = _flow(
        queries: _MembershipQueries(
          getMyHandler: (_) async => _slice(state: wireState),
        ),
        commands: _MembershipCommands(),
      );

      await flow.load();

      expect(
        flow.state.status,
        wireState == CircleGroupMembershipState.pending
            ? CircleGroupMembershipViewStatus.pending
            : CircleGroupMembershipViewStatus.active,
      );
    }
  });

  test(
    'apply and leave map command receipts without local success synthesis',
    () async {
      final commands = _MembershipCommands(
        applyHandler: (_) async =>
            _result(state: CircleGroupMembershipState.pending),
        leaveHandler: (_) async =>
            _result(state: CircleGroupMembershipState.left),
      );
      final joinFlow = _flow(
        queries: _MembershipQueries(
          getMyHandler: (_) async => throw const _MembershipMissing(),
        ),
        commands: commands,
      );
      await joinFlow.load();
      await joinFlow.apply();
      expect(joinFlow.state.status, CircleGroupMembershipViewStatus.pending);

      final leaveFlow = _flow(
        queries: _MembershipQueries(
          getMyHandler: (_) async =>
              _slice(state: CircleGroupMembershipState.active),
        ),
        commands: commands,
      );
      await leaveFlow.load();
      await leaveFlow.leave();
      expect(leaveFlow.state.status, CircleGroupMembershipViewStatus.left);
    },
  );

  test('failed load retries the same typed query and recovers', () async {
    var attempts = 0;
    final flow = _flow(
      queries: _MembershipQueries(
        getMyHandler: (_) async {
          attempts++;
          if (attempts == 1) throw StateError('temporary failure');
          return _slice(state: CircleGroupMembershipState.active);
        },
      ),
      commands: _MembershipCommands(),
    );

    await flow.load();
    expect(flow.state.status, CircleGroupMembershipViewStatus.failed);
    expect(flow.state.recoveryAction, CircleGroupMembershipRecoveryAction.load);

    await flow.retry();
    expect(flow.state.status, CircleGroupMembershipViewStatus.active);
    expect(attempts, 2);
  });

  test('concurrent load and apply calls use one in-flight operation', () async {
    var queryCalls = 0;
    var applyCalls = 0;
    final queryResult = Completer<CircleGroupMembershipSlice>();
    final applyResult = Completer<CircleGroupMembershipCommandResult>();
    final flow = _flow(
      queries: _MembershipQueries(
        getMyHandler: (_) {
          queryCalls++;
          return queryResult.future;
        },
      ),
      commands: _MembershipCommands(
        applyHandler: (_) {
          applyCalls++;
          return applyResult.future;
        },
      ),
    );

    final firstLoad = flow.load();
    final duplicateLoad = flow.load();
    expect(queryCalls, 1);
    queryResult.completeError(const _MembershipMissing());
    await Future.wait(<Future<void>>[firstLoad, duplicateLoad]);

    final firstApply = flow.apply();
    final duplicateApply = flow.apply();
    expect(applyCalls, 1);
    applyResult.complete(_result(state: CircleGroupMembershipState.pending));
    await Future.wait(<Future<void>>[firstApply, duplicateApply]);
    expect(flow.state.status, CircleGroupMembershipViewStatus.pending);
  });
}

CircleGroupMembershipFlow _flow({
  required CircleGroupMembershipQueries queries,
  required CircleGroupMembershipCommands commands,
  List<CircleGroupMembershipViewState>? states,
}) => CircleGroupMembershipFlow(
  circleId: 'circle-1',
  groupId: 'group-1',
  access: CircleGroupMembershipAccess(
    commands: commands,
    queries: queries,
    isAbsent: (error) => error is _MembershipMissing,
  ),
  onStateChanged: states?.add ?? (_) {},
);

CircleGroupMembershipSlice _slice({
  required CircleGroupMembershipState state,
}) => CircleGroupMembershipSlice(
  membershipId: 'membership-1',
  version: 3,
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

CircleGroupMembershipCommandResult _result({
  required CircleGroupMembershipState state,
}) => CircleGroupMembershipCommandResult(
  membershipId: 'membership-1',
  version: 4,
  role: CircleGroupMembershipRole.member,
  state: state,
  idempotentReplay: false,
);

final class _MembershipMissing implements Exception {
  const _MembershipMissing();
}

final class _MembershipQueries implements CircleGroupMembershipQueries {
  const _MembershipQueries({required this.getMyHandler});

  final Future<CircleGroupMembershipSlice?> Function(
    MyCircleGroupMembershipQuery query,
  )
  getMyHandler;

  @override
  Future<CircleGroupMembershipSlice> getMy(
    MyCircleGroupMembershipQuery query,
  ) async => (await getMyHandler(query))!;

  @override
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  ) async => CircleGroupMembershipPageSlice(
    items: <CircleGroupMembershipSlice>[],
  );
}

final class _MembershipCommands implements CircleGroupMembershipCommands {
  _MembershipCommands({this.applyHandler, this.leaveHandler});

  final Future<CircleGroupMembershipCommandResult> Function(
    ApplyCircleGroupMembershipCommand command,
  )?
  applyHandler;
  final Future<CircleGroupMembershipCommandResult> Function(
    LeaveCircleGroupMembershipCommand command,
  )?
  leaveHandler;

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) =>
      applyHandler?.call(command) ??
      Future<CircleGroupMembershipCommandResult>.error(
        UnsupportedError('apply'),
      );

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) =>
      leaveHandler?.call(command) ??
      Future<CircleGroupMembershipCommandResult>.error(
        UnsupportedError('leave'),
      );

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

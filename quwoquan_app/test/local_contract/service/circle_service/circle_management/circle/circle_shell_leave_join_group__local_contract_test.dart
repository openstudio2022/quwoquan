// 建联断点修复的行为契约：退出圈子（先退群再退圈、失败回滚、角色可见性）、
// 入圈自动申请默认公共群、游客加入登录续接一次、讨论区绑定未就绪的诚实等待态。
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001.t4
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#req-004
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/circle_shell_presentation_slots.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_shell.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

const String _circleId = 'fixture_circle_photo';
const String _defaultGroupId = '${_circleId}_public';

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'circle-leave-test-token',
    refreshToken: 'circle-leave-test-refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
    accountState: 'active',
    identityOrigin: 'widget-test',
    installId: 'circle-leave-widget-test-install',
  );
}

class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}

/// 游客起步、可翻转为已登录的会话双子（登录续接用例）。
class _FlippableCircleSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'circle-join-test-token',
      refreshToken: 'circle-join-test-refresh-token',
      ownerId: 'user_001',
      activePersonaId: 'user_001',
      accountState: 'active',
      identityOrigin: 'widget-test',
      installId: 'circle-join-widget-test-install',
    );
  }
}

final class _MembershipQueryDouble implements CircleMembershipQueries {
  _MembershipQueryDouble({
    this.role = CircleMemberRole.member,
    this.absent = false,
  });

  final CircleMemberRole role;
  final bool absent;

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) async {
    if (absent) {
      throw _membershipNotFoundException();
    }
    return CircleMembershipSlice(
      membershipId: '${query.circleId}_user_001',
      version: 1,
      circleId: query.circleId,
      personaId: 'user_001',
      role: role,
      state: CircleMembershipState.active,
      joinedAt: DateTime.utc(2026, 5, 6),
      leftAt: null,
      lastActiveAt: DateTime.utc(2026, 5, 6),
      contribution: 0,
      createdAt: DateTime.utc(2026, 5, 6),
      updatedAt: DateTime.utc(2026, 5, 6),
    );
  }

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => CircleMembershipPageSlice(items: const <CircleMembershipSlice>[]);

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => PersonaCirclePageSlice(items: const <PersonaCircleSlice>[]);
}

final class _AbsentMembershipError extends Error {}

/// loadCircle 只吞 canonical membership_not_found；absent 语义必须同码。
CloudException _membershipNotFoundException() {
  const errorCode = CircleMembershipErrorCode.membershipNotFound;
  return CloudException(
    type: CloudErrorType.notFound,
    message: errorCode.code,
    statusCode: errorCode.httpStatus,
    code: errorCode.code,
    domainErrorCode: DomainErrorCodeRegistry.fromCode(errorCode.code),
    runtimeFailure: RuntimeFailure(
      code: errorCode.code,
      semanticReason: 'membership_not_found',
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.validation,
      nature: RuntimeFailureNature.requiresUserAction,
      location: const RuntimeFailureLocation(
        businessObject: 'circle.circle_membership',
        functionModule: 'circle_membership_test_double',
      ),
      context: const RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[],
      ),
      recovery: const RuntimeRecoveryDirective.none(),
    ),
    userMessage: errorCode.defaultMessage,
  );
}

final class _RecordingCircleMembershipCommands
    implements CircleMembershipCommands {
  _RecordingCircleMembershipCommands({required this.callLog});

  final List<String> callLog;
  int _version = 0;
  CircleMembershipState joinResultState = CircleMembershipState.active;
  Completer<void>? joinGate;
  Object? joinError;

  @override
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  ) async {
    callLog.add('circle.join');
    await joinGate?.future;
    final error = joinError;
    if (error != null) throw error;
    return CircleMembershipCommandResult(
      membershipId: 'fixture_membership',
      version: ++_version,
      state: joinResultState,
      role: CircleMemberRole.member,
      idempotentReplay: false,
    );
  }

  @override
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  ) async {
    callLog.add('circle.leave');
    return CircleMembershipCommandResult(
      membershipId: 'fixture_membership',
      version: ++_version,
      state: CircleMembershipState.left,
      role: CircleMemberRole.member,
      idempotentReplay: false,
    );
  }

  @override
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  ) async => CircleMembershipCommandResult(
    membershipId: 'fixture_membership',
    version: ++_version,
    state: CircleMembershipState.active,
    role: command.role,
    idempotentReplay: false,
  );
}

final class _GroupMembershipCommandsDouble
    implements CircleGroupMembershipCommands {
  _GroupMembershipCommandsDouble({
    required this.callLog,
    this.failLeave = false,
  });

  final List<String> callLog;
  final bool failLeave;

  CircleGroupMembershipCommandResult _result(
    CircleGroupMembershipState state,
  ) => CircleGroupMembershipCommandResult(
    membershipId: 'fixture_group_membership',
    version: 2,
    role: CircleGroupMembershipRole.member,
    state: state,
    idempotentReplay: false,
  );

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) async {
    callLog.add('group.apply:${command.groupId}');
    return _result(CircleGroupMembershipState.active);
  }

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) async {
    callLog.add('group.leave:${command.groupId}');
    if (failLeave) {
      throw StateError('group leave rejected');
    }
    return _result(CircleGroupMembershipState.left);
  }

  @override
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  ) async => _result(CircleGroupMembershipState.active);

  @override
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  ) async => _result(CircleGroupMembershipState.rejected);

  @override
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  ) async => _result(CircleGroupMembershipState.removed);

  @override
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  ) async => _result(CircleGroupMembershipState.active);
}

final class _GroupMembershipQueriesDouble
    implements CircleGroupMembershipQueries {
  _GroupMembershipQueriesDouble({this.myState});

  /// null 表示尚未加入（getMy 抛 absent 语义错误）。
  final CircleGroupMembershipState? myState;

  @override
  Future<CircleGroupMembershipSlice> getMy(
    MyCircleGroupMembershipQuery query,
  ) async {
    final state = myState;
    if (state == null) {
      throw _AbsentMembershipError();
    }
    return CircleGroupMembershipSlice(
      membershipId: 'fixture_group_membership',
      version: 1,
      groupId: query.groupId,
      circleId: query.circleId,
      personaId: 'user_001',
      role: CircleGroupMembershipRole.member,
      state: state,
      joinedAt: DateTime.utc(2026, 5, 6),
      leftAt: null,
      decidedAt: null,
      createdAt: DateTime.utc(2026, 5, 6),
      updatedAt: DateTime.utc(2026, 5, 6),
    );
  }

  @override
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  ) async => CircleGroupMembershipPageSlice(
    items: const <CircleGroupMembershipSlice>[],
  );
}

final class _GroupQueryDouble implements CircleGroupQueries {
  const _GroupQueryDouble({this.conversationId = 'fixture_conv_circle_photo'});

  final String? conversationId;

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) async =>
      CircleGroupSlice(
        groupId: query.groupId,
        version: 1,
        circleId: query.circleId,
        parentGroupId: null,
        groupType: CircleGroupType.publicGroup,
        nodeType: null,
        name: '默认公共群',
        description: '',
        visibility: CircleGroupVisibility.public,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        conversationId: conversationId,
        storageEnabled: false,
        noticeEnabled: true,
        isDefaultPublicGroup: true,
        status: CircleGroupStatus.active,
        memberCount: 1,
        createdAt: DateTime.utc(2026, 5, 6),
        updatedAt: DateTime.utc(2026, 5, 6),
      );

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async =>
      CircleGroupPageSlice(items: const <CircleGroupSlice>[]);

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async =>
      CircleGroupPageSlice(items: const <CircleGroupSlice>[]);
}

final class _RecordingBehaviorFactWriter implements CircleBehaviorFactAppender {
  final List<BehaviorEventType> events = <BehaviorEventType>[];

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {
    events.add(command.eventType);
  }
}

final class _SilentExceptionTelemetry implements ExceptionTelemetryPort {
  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {}

  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {}

  @override
  Future<void> flushPending() async {}
}

CircleGroupMembershipAccess _groupAccess({
  required List<String> callLog,
  CircleGroupMembershipState? myState,
  bool failLeave = false,
}) => CircleGroupMembershipAccess(
  commands: _GroupMembershipCommandsDouble(
    callLog: callLog,
    failLeave: failLeave,
  ),
  queries: _GroupMembershipQueriesDouble(myState: myState),
  isAbsent: (error) => error is _AbsentMembershipError,
);

Widget _scopedShell({
  required List<Override> overrides,
  CircleGroupQueries groupQuery = const _GroupQueryDouble(),
  CircleBehaviorFactAppender? behaviorWriter,
}) {
  return ProviderScope(
    overrides: [
      circlesListQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
      circleDetailQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
      circleDetailGroupQueryProvider.overrideWithValue(groupQuery),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'user_001',
          ownerUserId: 'user_001',
          displayName: '圈子测试用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(
        behaviorWriter ?? _RecordingBehaviorFactWriter(),
      ),
      behaviorRepositoryProvider.overrideWithValue(
        RecordingContentBehaviorRepository(),
      ),
      exceptionTelemetryPortProvider.overrideWithValue(
        _SilentExceptionTelemetry(),
      ),
      ...overrides,
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(
              body: CircleShell(
                circleId: _circleId,
                participantSlots: buildCircleShellParticipantSlots(
                  membershipApprovalPageBuilder: (_) => const SizedBox.shrink(),
                ),
              ),
            ),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
          GoRoute(
            path: AppRoutePaths.loginPathTemplate,
            builder: (_, _) =>
                const Text('LOGIN', textDirection: TextDirection.ltr),
          ),
        ],
      ),
    ),
  );
}

Future<void> _pump(
  WidgetTester tester, {
  required List<Override> overrides,
  CircleGroupQueries groupQuery = const _GroupQueryDouble(),
  CircleBehaviorFactAppender? behaviorWriter,
}) async {
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    _scopedShell(
      overrides: overrides,
      groupQuery: groupQuery,
      behaviorWriter: behaviorWriter,
    ),
  );
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 350));
}

Future<void> _openMoreMenu(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey<String>('object-chrome-more')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  group('退出圈子', () {
    testWidgets('成员确认退出后先退默认群再退圈，CTA 回到可加入', (tester) async {
      final callLog = <String>[];
      final behaviorWriter = _RecordingBehaviorFactWriter();
      await _pump(
        tester,
        behaviorWriter: behaviorWriter,
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: callLog),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(
              callLog: callLog,
              myState: CircleGroupMembershipState.active,
            ),
          ),
        ],
      );

      await _openMoreMenu(tester);
      expect(find.text(CommunityText.leaveCircleAction), findsOneWidget);
      await tester.tap(find.text(CommunityText.leaveCircleAction));
      await tester.pumpAndSettle();

      expect(find.text(CommunityText.circleLeaveConfirmTitle), findsOneWidget);
      await tester.tap(
        find.byKey(const ValueKey<String>('circle-leave-confirm')),
      );
      await tester.pumpAndSettle();

      expect(callLog, <String>['group.leave:$_defaultGroupId', 'circle.leave']);
      expect(find.text(CommunityText.joinCircle), findsWidgets);
      // 行为事实链路：退出成功后发出 leaveCircle 事实（推荐 HotPath 信号）。
      expect(behaviorWriter.events, contains(BehaviorEventType.leaveCircle));
      // 成功 toast 的自动消隐计时器走完，避免测试尾部 pending timer。
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('默认群退出失败时整体中止且不退圈', (tester) async {
      final callLog = <String>[];
      await _pump(
        tester,
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: callLog),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(
              callLog: callLog,
              myState: CircleGroupMembershipState.active,
              failLeave: true,
            ),
          ),
        ],
      );

      await _openMoreMenu(tester);
      await tester.tap(find.text(CommunityText.leaveCircleAction));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey<String>('circle-leave-confirm')),
      );
      await tester.pumpAndSettle();

      expect(callLog, <String>['group.leave:$_defaultGroupId']);
      expect(callLog, isNot(contains('circle.leave')));
      // 状态回滚：仍是成员（CTA 保持已加入态）。
      expect(find.text(CommunityText.joinedCircle), findsWidgets);
    });

    testWidgets('圈主更多菜单不提供退出圈子', (tester) async {
      await _pump(
        tester,
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(role: CircleMemberRole.owner),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: <String>[]),
          ),
        ],
      );

      await _openMoreMenu(tester);
      expect(find.text(CommunityText.leaveCircleAction), findsNothing);
    });

    testWidgets('游客更多菜单不提供退出圈子', (tester) async {
      await _pump(
        tester,
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_GuestSession.new),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(absent: true),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: <String>[]),
          ),
        ],
      );

      await _openMoreMenu(tester);
      expect(find.text(CommunityText.leaveCircleAction), findsNothing);
    });
  });

  group('入圈即入群', () {
    // gwt-001 t1..t4：加入先即时反馈成员态（乐观），失败恢复原成员状态并
    // 携带 canonical failure，不追加行为事实、不触发入群（不产生伪成功）。
    testWidgets('加入失败恢复原成员状态并返回 canonical failure 不伪成功', (tester) async {
      final callLog = <String>[];
      final behaviorWriter = _RecordingBehaviorFactWriter();
      final commands = _RecordingCircleMembershipCommands(callLog: callLog)
        ..joinGate = Completer<void>()
        ..joinError = _membershipNotFoundException();
      final container = ProviderContainer(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailQueryProvider.overrideWithValue(
            InMemoryCircleQueryReader(),
          ),
          circleDetailGroupQueryProvider.overrideWithValue(
            const _GroupQueryDouble(),
          ),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(absent: true),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            commands,
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(callLog: callLog, myState: null),
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '圈子测试用户',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          circleDetailBehaviorFactWriterProvider.overrideWithValue(
            behaviorWriter,
          ),
          exceptionTelemetryPortProvider.overrideWithValue(
            _SilentExceptionTelemetry(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(circleStateProvider(_circleId).notifier);
      await notifier.loadCircle();
      final previousStatus = container
          .read(circleStateProvider(_circleId))
          .joinStatus;

      final joinFuture = notifier.joinCircle();
      // t1：命令未返回前界面已先反馈成员进行中/已加入态（乐观反馈，
      // joinCircle 首个 await 前同步生效）。
      expect(
        container.read(circleStateProvider(_circleId)).joinStatus,
        'joined',
      );

      commands.joinGate!.complete();
      await joinFuture;

      final state = container.read(circleStateProvider(_circleId));
      // t2：失败后恢复原成员状态。
      expect(state.joinStatus, previousStatus);
      // t3：canonical failure 进入错误呈现链（AppSectionErrorCard 消费）。
      expect(state.loadError, isA<CloudException>());
      // t4：不产生伪成功事实——无行为事实追加、不触发默认群自动申请。
      expect(behaviorWriter.events, isEmpty);
      expect(callLog, <String>['circle.join']);
    });

    testWidgets('open 圈子加入成功后自动申请默认公共群', (tester) async {
      final callLog = <String>[];
      final container = ProviderContainer(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailQueryProvider.overrideWithValue(
            InMemoryCircleQueryReader(),
          ),
          circleDetailGroupQueryProvider.overrideWithValue(
            const _GroupQueryDouble(),
          ),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(absent: true),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: callLog),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(callLog: callLog, myState: null),
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '圈子测试用户',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          circleDetailBehaviorFactWriterProvider.overrideWithValue(
            _RecordingBehaviorFactWriter(),
          ),
          exceptionTelemetryPortProvider.overrideWithValue(
            _SilentExceptionTelemetry(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(circleStateProvider(_circleId).notifier);
      await notifier.loadCircle();
      await notifier.joinCircle();

      expect(callLog, <String>['circle.join', 'group.apply:$_defaultGroupId']);
      expect(
        container.read(circleStateProvider(_circleId)).defaultPublicGroup,
        isNotNull,
      );
    });

    testWidgets('群自动申请失败不回滚圈子加入', (tester) async {
      final callLog = <String>[];
      final container = ProviderContainer(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailQueryProvider.overrideWithValue(
            InMemoryCircleQueryReader(),
          ),
          circleDetailGroupQueryProvider.overrideWithValue(
            const _GroupQueryDouble(),
          ),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(absent: true),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: callLog),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            CircleGroupMembershipAccess(
              commands: _ThrowingGroupCommands(callLog: callLog),
              queries: _GroupMembershipQueriesDouble(myState: null),
              isAbsent: (error) => error is _AbsentMembershipError,
            ),
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '圈子测试用户',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          circleDetailBehaviorFactWriterProvider.overrideWithValue(
            _RecordingBehaviorFactWriter(),
          ),
          exceptionTelemetryPortProvider.overrideWithValue(
            _SilentExceptionTelemetry(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(circleStateProvider(_circleId).notifier);
      await notifier.loadCircle();
      await notifier.joinCircle();

      final state = container.read(circleStateProvider(_circleId));
      expect(state.joinStatus, 'joined');
      expect(state.loadError, isNull);
      expect(callLog, contains('circle.join'));
    });
  });

  group('游客加入登录续接', () {
    testWidgets('游客点加入先登记续接，登录成功后只续接一次加入', (tester) async {
      final callLog = <String>[];
      await _pump(
        tester,
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(
            _FlippableCircleSession.new,
          ),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(absent: true),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: callLog),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(callLog: callLog, myState: null),
          ),
        ],
      );

      final container = ProviderScope.containerOf(
        tester.element(find.byType(CircleShell)),
      );

      await tester.tap(find.text(CommunityText.joinCircle).first);
      await tester.pumpAndSettle();

      // 游客态：不直接提交加入，先登记续接并进入登录页。
      expect(callLog, isEmpty);
      expect(find.text('LOGIN'), findsOneWidget);
      (container.read(
        authSessionControllerProvider.notifier,
      ) as _FlippableCircleSession).loginNow();
      await tester.pumpAndSettle();

      // 登录成功：只续接一次加入（open 圈子收敛 active，随后自动申请默认群）。
      expect(
        callLog.where((call) => call == 'circle.join').length,
        1,
        reason: '加入续接必须 one-shot',
      );
      await tester.pumpAndSettle();
      expect(callLog.where((call) => call == 'circle.join').length, 1);
    });
  });

  group('讨论区绑定未就绪', () {
    testWidgets('有默认群但会话未绑定时显示开通中与重试', (tester) async {
      await _pump(
        tester,
        groupQuery: const _GroupQueryDouble(conversationId: null),
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          circleDetailMembershipQueryProvider.overrideWithValue(
            _MembershipQueryDouble(),
          ),
          circleDetailMembershipCommandWriterProvider.overrideWithValue(
            _RecordingCircleMembershipCommands(callLog: <String>[]),
          ),
          circleDetailGroupMembershipAccessProvider.overrideWithValue(
            _groupAccess(
              callLog: <String>[],
              myState: CircleGroupMembershipState.active,
            ),
          ),
        ],
      );

      await tester.tap(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text(ObjectHomepageText.objectTabDiscussion),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('circle-chat-binding-pending')),
        findsOneWidget,
      );
      expect(
        find.text(CommunityText.circleChatBindingPendingTitle),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('circle-chat-binding-retry')),
        findsOneWidget,
      );
      expect(find.text(CommunityText.circleNoChatEnabled), findsNothing);

      await tester.tap(
        find.byKey(const ValueKey<String>('circle-chat-binding-retry')),
      );
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 350));
    });
  });
}

final class _ThrowingGroupCommands implements CircleGroupMembershipCommands {
  _ThrowingGroupCommands({required this.callLog});

  final List<String> callLog;

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) async {
    callLog.add('group.apply.failed:${command.groupId}');
    throw StateError('group apply rejected');
  }

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) async => throw StateError('unused');

  @override
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  ) async => throw StateError('unused');

  @override
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  ) async => throw StateError('unused');

  @override
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  ) async => throw StateError('unused');

  @override
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  ) async => throw StateError('unused');
}

// spec_ref: specs/feature-tree/circle-community/activity-member-governance/spec.md#sit-001
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart'
    show AppPageErrorState;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ContentText, SearchText;
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show
        circleDetailMembershipModerationWriterProvider,
        circleDetailPendingMembershipQueryProvider;
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/circle_membership_approval_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

/// GWT1（member-role-permission）本地分解：审批队列页消费
/// ListPendingCircleMemberships，Approve/Reject 经 ModerationWriter 提交，
/// 与云侧 api_integration `circle_membership__api_integration_test.go` 的
/// approve/reject 生命周期断言一一对应（R12/R13）。
void main() {
  const circleId = 'fixture_circle_approval';

  CircleMembershipSlice pending(
    String personaId, {
    String? membershipId,
    int version = 1,
  }) => CircleMembershipSlice(
    membershipId: membershipId ?? 'cm_$personaId',
    version: version,
    circleId: circleId,
    personaId: personaId,
    role: CircleMemberRole.member,
    state: CircleMembershipState.pending,
    joinedAt: DateTime.utc(2026, 7, 20),
    leftAt: null,
    lastActiveAt: null,
    contribution: 0,
    createdAt: DateTime.utc(2026, 7, 20),
    updatedAt: DateTime.utc(2026, 7, 20),
  );

  Widget host(_ApprovalFixture fixture) {
    final journeyEventTracker = JourneyEventTracker(
      telemetryReporter: RecordingAppTelemetryRecorder(),
    );
    return ProviderScope(
      overrides: [
        circleDetailPendingMembershipQueryProvider.overrideWithValue(fixture),
        circleDetailMembershipModerationWriterProvider.overrideWithValue(
          fixture,
        ),
      ],
      child: CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        home: CircleMembershipApprovalPage(
          circleId: circleId,
          pendingMemberships: fixture,
          moderationWriter: fixture,
          journeyEventTracker: journeyEventTracker,
        ),
      ),
    );
  }

  testWidgets('pending 队列渲染申请行并展示通过/拒绝操作', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
      pending('persona_b'),
    ]);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_b')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-reject-persona_a')),
      findsOneWidget,
    );
  });

  testWidgets('通过申请调用 approve 命令并从队列移除该行', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
    ]);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(fixture.approvedPersonaIds, <String>['persona_a']);
    expect(fixture.approvedClientRequestIds.single, isNotEmpty);
    expect(fixture.listQueries, hasLength(2));
    expect(fixture.listQueries.last.cursor, isNull);
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-empty')),
      findsOneWidget,
    );
    // 排空结果 toast 的自动消隐 timer。
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  });

  testWidgets('拒绝申请调用 reject 命令并从队列移除该行', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
    ]);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-reject-persona_a')),
    );
    await tester.pumpAndSettle();

    expect(fixture.rejectedPersonaIds, <String>['persona_a']);
    expect(fixture.rejectedClientRequestIds.single, isNotEmpty);
    expect(fixture.listQueries, hasLength(2));
    expect(fixture.listQueries.last.cursor, isNull);
    expect(
      find.byKey(const ValueKey<String>('circle-approval-empty')),
      findsOneWidget,
    );
    // 排空结果 toast 的自动消隐 timer。
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  });

  testWidgets('空队列展示空态而非空白', (tester) async {
    final fixture = _ApprovalFixture(const <CircleMembershipSlice>[]);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-empty')),
      findsOneWidget,
    );
  });

  testWidgets('加载失败展示页面错误态并可重试恢复', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
    ], failFirstLoad: true);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);

    await tester.tap(find.text(SearchText.reload).first);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
  });

  testWidgets('typed ACK 后从 cursor=null 遍历完整 Remote 队列再移除目标', (tester) async {
    final lastReadbackPage = Completer<CircleMembershipPageSlice>();
    final fixture = _ApprovalFixture(
      <CircleMembershipSlice>[pending('persona_a'), pending('persona_b')],
      onList: (query, call) {
        if (call == 1) {
          return Future.value(
            CircleMembershipPageSlice(
              items: <CircleMembershipSlice>[
                pending('persona_a'),
                pending('persona_b'),
              ],
            ),
          );
        }
        if (call == 2) {
          expect(query.cursor, isNull);
          return Future.value(
            CircleMembershipPageSlice(
              items: <CircleMembershipSlice>[pending('persona_b')],
              cursor: 'readback-next',
            ),
          );
        }
        expect(query.cursor, 'readback-next');
        return lastReadbackPage.future;
      },
    );
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
    );
    await tester.pump();

    expect(fixture.listQueries, hasLength(3));
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
      reason: '全量 authoritative readback 完成前必须保留 last-confirmed 行',
    );

    lastReadbackPage.complete(
      CircleMembershipPageSlice(
        items: <CircleMembershipSlice>[
          pending('persona_b'),
          pending('persona_c'),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_b')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_c')),
      findsOneWidget,
    );
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  });

  testWidgets('命令失败保留行且显式 retry 复用同一 clientRequestId', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
    ], failApproveAttempts: 1);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    expect(find.text(ContentText.tryAgain), findsOneWidget);
    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();

    expect(fixture.approvedClientRequestIds, hasLength(2));
    expect(
      fixture.approvedClientRequestIds.toSet(),
      hasLength(1),
      reason: '显式 retry 必须重放同一次用户意图',
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsNothing,
    );
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  });

  testWidgets('readback 失败保留 last-confirmed 并以相同请求身份重试', (tester) async {
    final fixture = _ApprovalFixture(
      <CircleMembershipSlice>[pending('persona_a')],
      failLoadCalls: <int>{2},
    );
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();

    expect(fixture.approvedClientRequestIds, hasLength(2));
    expect(fixture.approvedClientRequestIds.toSet(), hasLength(1));
    expect(fixture.listQueries[1].cursor, isNull);
    expect(fixture.listQueries[2].cursor, isNull);
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsNothing,
    );
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  });

  testWidgets('未收敛或错误 typed ACK 不删除 last-confirmed 行', (tester) async {
    final fixture = _ApprovalFixture(<CircleMembershipSlice>[
      pending('persona_a'),
    ], invalidApproveAck: true);
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-approval-approve-persona_a')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(fixture.listQueries, hasLength(1));
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    expect(find.text(ContentText.tryAgain), findsOneWidget);
  });

  testWidgets('load-more 失败不遮蔽已确认行，retry 后按 membership/version 去重', (
    tester,
  ) async {
    final fixture = _ApprovalFixture(
      <CircleMembershipSlice>[pending('persona_a')],
      onList: (query, call) async {
        if (call == 1) {
          return CircleMembershipPageSlice(
            items: <CircleMembershipSlice>[pending('persona_a')],
            cursor: 'page-2',
          );
        }
        expect(query.cursor, 'page-2');
        if (call == 2) {
          throw StateError('load more unavailable');
        }
        return CircleMembershipPageSlice(
          items: <CircleMembershipSlice>[
            pending('persona_a'),
            pending('persona_a', version: 2),
            pending('persona_b'),
            pending('persona_b'),
          ],
        );
      },
    );
    await tester.pumpWidget(host(fixture));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-load-more-error')),
      findsOneWidget,
    );

    await tester.tap(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('circle-approval-load-more-error'),
        ),
        matching: find.byType(CupertinoButton),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_a')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_b')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-load-more-error')),
      findsNothing,
    );
  });

  testWidgets('晚到旧 reset 不能覆盖新 query owner 的已确认快照', (tester) async {
    final oldResult = Completer<CircleMembershipPageSlice>();
    final newResult = Completer<CircleMembershipPageSlice>();
    final oldFixture = _ApprovalFixture(
      const <CircleMembershipSlice>[],
      onList: (_, _) => oldResult.future,
    );
    final newFixture = _ApprovalFixture(
      const <CircleMembershipSlice>[],
      onList: (_, _) => newResult.future,
    );

    await tester.pumpWidget(host(oldFixture));
    await tester.pump();
    await tester.pumpWidget(host(newFixture));
    await tester.pump();

    newResult.complete(
      CircleMembershipPageSlice(
        items: <CircleMembershipSlice>[pending('persona_new')],
      ),
    );
    await tester.pump();
    oldResult.complete(
      CircleMembershipPageSlice(
        items: <CircleMembershipSlice>[pending('persona_old')],
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_new')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-approval-row-persona_old')),
      findsNothing,
    );
  });
}

typedef _PendingListHandler =
    Future<CircleMembershipPageSlice> Function(
      PendingCircleMembershipListQuery query,
      int call,
    );

final class _ApprovalFixture
    implements
        PendingCircleMemberships,
        ClientRequestBoundCircleMembershipModeration {
  _ApprovalFixture(
    List<CircleMembershipSlice> seed, {
    bool failFirstLoad = false,
    Set<int> failLoadCalls = const <int>{},
    int failApproveAttempts = 0,
    this.invalidApproveAck = false,
    this.onList,
  }) : _pending = List<CircleMembershipSlice>.of(seed),
       _failLoadCalls = <int>{...failLoadCalls, if (failFirstLoad) 1},
       _remainingApproveFailures = failApproveAttempts;

  final List<CircleMembershipSlice> _pending;
  final Set<int> _failLoadCalls;
  final bool invalidApproveAck;
  final _PendingListHandler? onList;
  final List<String> approvedPersonaIds = <String>[];
  final List<String> rejectedPersonaIds = <String>[];
  final List<String> approvedClientRequestIds = <String>[];
  final List<String> rejectedClientRequestIds = <String>[];
  final List<PendingCircleMembershipListQuery> listQueries =
      <PendingCircleMembershipListQuery>[];
  final Map<String, CircleMembershipCommandResult> _resultsByClientRequestId =
      <String, CircleMembershipCommandResult>{};
  int _remainingApproveFailures;
  int _loadCalls = 0;

  @override
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  ) async {
    _loadCalls++;
    listQueries.add(query);
    if (_failLoadCalls.contains(_loadCalls)) {
      throw StateError('pending queue load failed');
    }
    final handler = onList;
    if (handler != null) {
      return handler(query, _loadCalls);
    }
    return CircleMembershipPageSlice(
      items: _pending
          .where((item) => item.circleId == query.circleId)
          .toList(growable: false),
    );
  }

  @override
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  ) => Future<CircleMembershipCommandResult>.error(
    StateError('legacy approve must not be used by the approval page'),
  );

  @override
  Future<CircleMembershipCommandResult> approveWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  }) async {
    approvedPersonaIds.add(command.personaId);
    approvedClientRequestIds.add(clientRequestId);
    if (_remainingApproveFailures > 0) {
      _remainingApproveFailures--;
      throw StateError('approve temporarily unavailable');
    }
    return _decide(
      command,
      CircleMembershipState.active,
      clientRequestId: clientRequestId,
      invalidAck: invalidApproveAck,
    );
  }

  @override
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  ) => Future<CircleMembershipCommandResult>.error(
    StateError('legacy reject must not be used by the approval page'),
  );

  @override
  Future<CircleMembershipCommandResult> rejectWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  }) async {
    rejectedPersonaIds.add(command.personaId);
    rejectedClientRequestIds.add(clientRequestId);
    return _decide(
      command,
      CircleMembershipState.rejected,
      clientRequestId: clientRequestId,
    );
  }

  CircleMembershipCommandResult _decide(
    DecideCircleMembershipCommand command,
    CircleMembershipState state, {
    required String clientRequestId,
    bool invalidAck = false,
  }) {
    final replay = _resultsByClientRequestId[clientRequestId];
    if (replay != null) {
      return CircleMembershipCommandResult(
        membershipId: replay.membershipId,
        version: replay.version,
        state: replay.state,
        role: replay.role,
        idempotentReplay: true,
      );
    }
    final index = _pending.indexWhere(
      (item) => item.personaId == command.personaId,
    );
    if (index < 0) {
      throw StateError('pending membership not found');
    }
    final target = _pending.removeAt(index);
    final result = CircleMembershipCommandResult(
      membershipId: invalidAck
          ? 'unexpected_${target.membershipId}'
          : target.membershipId,
      version: target.version + 1,
      state: state,
      role: target.role,
      idempotentReplay: false,
    );
    _resultsByClientRequestId[clientRequestId] = result;
    return result;
  }
}

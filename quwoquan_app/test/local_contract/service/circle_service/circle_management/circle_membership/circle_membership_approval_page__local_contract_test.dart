// spec_ref: specs/feature-tree/circle-community/activity-member-governance/spec.md#sit-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart'
    show AppPageErrorState;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart' show SearchText;
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

  CircleMembershipSlice pending(String personaId) => CircleMembershipSlice(
    membershipId: 'cm_$personaId',
    version: 1,
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
    await tester.pumpAndSettle();

    expect(fixture.approvedPersonaIds, <String>['persona_a']);
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
}

final class _ApprovalFixture
    implements PendingCircleMemberships, CircleMembershipModeration {
  _ApprovalFixture(
    List<CircleMembershipSlice> seed, {
    this.failFirstLoad = false,
  }) : _pending = List<CircleMembershipSlice>.of(seed);

  final List<CircleMembershipSlice> _pending;
  final bool failFirstLoad;
  final List<String> approvedPersonaIds = <String>[];
  final List<String> rejectedPersonaIds = <String>[];
  int _loadCalls = 0;

  @override
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  ) async {
    _loadCalls++;
    if (failFirstLoad && _loadCalls == 1) {
      throw StateError('pending queue load failed');
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
  ) async {
    approvedPersonaIds.add(command.personaId);
    return _decide(command, CircleMembershipState.active);
  }

  @override
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  ) async {
    rejectedPersonaIds.add(command.personaId);
    return _decide(command, CircleMembershipState.rejected);
  }

  CircleMembershipCommandResult _decide(
    DecideCircleMembershipCommand command,
    CircleMembershipState state,
  ) {
    final index = _pending.indexWhere(
      (item) => item.personaId == command.personaId,
    );
    if (index < 0) {
      throw StateError('pending membership not found');
    }
    final target = _pending.removeAt(index);
    return CircleMembershipCommandResult(
      membershipId: target.membershipId,
      version: target.version + 1,
      state: state,
      role: target.role,
      idempotentReplay: false,
    );
  }
}

// readiness_case: circle_membership_approval_app_uat
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-004
/// 两个 disposable actor 经公开 Circle API 建立 approval 圈子与真实 pending
/// membership，再由 production App 审批并以 Remote 队列、成员版本和 memberCount
/// 权威读回确认收敛。
///
/// readiness_case 已登记（operations.yaml `circle_membership_approval_app_uat`）。
/// 执行仍要求健康 gamma-local 与 Android/iPhone 物理 ResultBundle；环境或真机
/// 缺失时保持 OPEN-004 BLOCK，不得用模拟器或 fixture 冒充。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/circle_membership_approval_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _disposableActorsConfirmed = bool.fromEnvironment(
  'QWQ_CIRCLE_MEMBERSHIP_DISPOSABLE_ACTORS_ACK',
);
const _moreActionKey = ValueKey<String>('object-chrome-more');

void main() {
  patrolTest(
    'circle_membership_remote_owner_approves_pending_actor_and_readback',
    tags: const ['user-acceptance', 'circle', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final ownerHarness = await CircleApiContractHarness.create();
      CircleApiContractHarness? applicantHarness;
      AuthSessionGrant? owner;
      AuthSessionGrant? applicant;
      String? circleId;
      var applicantActivated = false;

      try {
        applicantHarness = await CircleApiContractHarness.create();
        owner = await ownerHarness.loginDisposableAccount(
          'membership-approval-owner-$suffix',
        );
        applicant = await applicantHarness.loginDisposableAccount(
          'membership-approval-applicant-$suffix',
        );
        final ownerPersonaId = owner.activePersona?.personaId.trim() ?? '';
        final applicantPersonaId =
            applicant.activePersona?.personaId.trim() ?? '';
        if (ownerPersonaId.isEmpty || applicantPersonaId.isEmpty) {
          throw StateError('Disposable accounts require active personas');
        }

        final created = await ownerHarness.withIdempotencyKey(
          'circle-membership-approval-create-$suffix',
          () => ownerHarness.lifecycle.createCircle(
            CreateCircleCommand(
              name: '真实审批圈 $suffix',
              category: 'interest',
              visibility: CircleVisibility.public.wireName,
              joinPolicy: CircleJoinPolicy.approval.wireName,
            ),
          ),
        );
        circleId = created.circleId;
        final initialCircle = await ownerHarness.query.get(
          CircleDetailQuery(circleId: circleId),
        );

        final pendingReceipt = await applicantHarness.withIdempotencyKey(
          'circle-membership-approval-join-$suffix',
          () => applicantHarness!.membership.join(
            JoinCircleMembershipCommand(circleId: circleId!),
          ),
        );
        if (pendingReceipt.state != CircleMembershipState.pending ||
            pendingReceipt.version <= 0 ||
            pendingReceipt.idempotentReplay) {
          throw StateError('JoinCircle did not create one pending membership');
        }
        final pendingSelf = await applicantHarness.membershipQueries
            .getMyMembership(MyCircleMembershipQuery(circleId: circleId));
        if (pendingSelf.membershipId != pendingReceipt.membershipId ||
            pendingSelf.personaId != applicantPersonaId ||
            pendingSelf.state != CircleMembershipState.pending ||
            pendingSelf.version != pendingReceipt.version) {
          throw StateError('Applicant pending membership readback drifted');
        }
        await _expectPendingMembership(
          ownerHarness,
          circleId: circleId,
          personaId: applicantPersonaId,
          membershipId: pendingReceipt.membershipId,
          version: pendingReceipt.version,
        );
        final pendingCircle = await ownerHarness.query.get(
          CircleDetailQuery(circleId: circleId),
        );
        if (pendingCircle.memberCount != initialCircle.memberCount) {
          throw StateError('Pending membership must not increment memberCount');
        }

        installPatrolAcceptanceSessionForRunner(
          accessToken: owner.accessToken,
          refreshToken: owner.refreshToken,
          ownerId: owner.ownerId,
          personaId: ownerPersonaId,
        );
        await launchPatrolAppOnce($);

        await patrolGoTo($, AppRoutePaths.circleDetail(id: circleId));
        await $(find.byType(CircleDetailPage)).waitUntilVisible();
        await $(find.byKey(_moreActionKey)).waitUntilVisible();
        await $(find.byKey(_moreActionKey)).tap();
        await $(
          find.text(CommunityText.circleApprovalTitle),
        ).waitUntilVisible();
        await $(find.text(CommunityText.circleApprovalTitle)).tap();
        await $(find.byType(CircleMembershipApprovalPage)).waitUntilVisible();

        final rowKey = ValueKey<String>(
          'circle-approval-row-$applicantPersonaId',
        );
        final approveKey = ValueKey<String>(
          'circle-approval-approve-$applicantPersonaId',
        );
        await $(find.byKey(rowKey)).waitUntilVisible();
        _expectNoApprovalFailure();
        await $(find.byKey(approveKey)).tap();
        await _waitUntilAbsent($, find.byKey(rowKey));
        await $(
          find.byKey(const ValueKey<String>('circle-approval-empty')),
        ).waitUntilVisible();
        _expectNoApprovalFailure();

        final activeSelf = await _waitForMembershipState(
          applicantHarness,
          circleId: circleId,
          expected: CircleMembershipState.active,
        );
        applicantActivated = true;
        if (activeSelf.membershipId != pendingReceipt.membershipId ||
            activeSelf.personaId != applicantPersonaId ||
            activeSelf.version <= pendingReceipt.version) {
          throw StateError('Approved membership version did not converge');
        }
        await _expectMembershipAbsentFromPending(
          ownerHarness,
          circleId: circleId,
          personaId: applicantPersonaId,
        );
        await _waitForMemberCount(
          ownerHarness,
          circleId: circleId,
          expected: initialCircle.memberCount + 1,
        );
      } finally {
        try {
          if (applicantActivated &&
              applicantHarness != null &&
              circleId != null) {
            await applicantHarness.withIdempotencyKey(
              'circle-membership-approval-leave-$suffix',
              () => applicantHarness!.membership.leave(
                LeaveCircleMembershipCommand(circleId: circleId!),
              ),
            );
          }
        } finally {
          try {
            if (circleId != null) {
              await ownerHarness.withIdempotencyKey(
                'circle-membership-approval-archive-$suffix',
                () => ownerHarness.lifecycle.archiveCircle(
                  ArchiveCircleCommand(circleId: circleId!),
                ),
              );
            }
          } finally {
            try {
              await applicantHarness?.close();
            } finally {
              await ownerHarness.close();
            }
          }
        }
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'CircleMembership UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'CircleMembership UAT installs its own disposable owner session',
    );
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'CircleMembership UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'CircleMembership UAT requires App and API to use the same gateway',
    );
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_CIRCLE_MEMBERSHIP_DISPOSABLE_ACTORS_ACK=true only when '
      'public CloseAccount cleanup is permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}

void _expectNoApprovalFailure() {
  expect(find.byType(AppPageErrorState), findsNothing);
  expect(find.byType(AppSectionErrorState), findsNothing);
}

Future<void> _waitUntilAbsent(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoApprovalFailure();
    if (finder.evaluate().isEmpty) return;
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('审批页未按 production Remote 权威读回移除已处理申请');
}

Future<CircleMembershipSlice> _expectPendingMembership(
  CircleApiContractHarness harness, {
  required String circleId,
  required String personaId,
  required String membershipId,
  required int version,
}) async {
  final found = await _findPendingMembership(
    harness,
    circleId: circleId,
    personaId: personaId,
  );
  if (found == null ||
      found.membershipId != membershipId ||
      found.version != version ||
      found.state != CircleMembershipState.pending) {
    throw StateError(
      'Owner pending queue did not expose the canonical request',
    );
  }
  return found;
}

Future<void> _expectMembershipAbsentFromPending(
  CircleApiContractHarness harness, {
  required String circleId,
  required String personaId,
}) async {
  final found = await _findPendingMembership(
    harness,
    circleId: circleId,
    personaId: personaId,
  );
  if (found != null) {
    throw StateError('Approved membership remains in the pending queue');
  }
}

Future<CircleMembershipSlice?> _findPendingMembership(
  CircleApiContractHarness harness, {
  required String circleId,
  required String personaId,
}) async {
  String? cursor;
  final seenCursors = <String>{};
  do {
    final page = await harness.pendingMemberships.listPendingMemberships(
      PendingCircleMembershipListQuery(
        circleId: circleId,
        cursor: cursor,
        limit: 100,
      ),
    );
    for (final item in page.items) {
      if (item.personaId == personaId) return item;
    }
    cursor = page.cursor?.trim();
    if (cursor != null && cursor.isNotEmpty && !seenCursors.add(cursor)) {
      throw StateError('Pending membership query returned a cursor cycle');
    }
  } while (cursor != null && cursor.isNotEmpty);
  return null;
}

Future<CircleMembershipSlice> _waitForMembershipState(
  CircleApiContractHarness harness, {
  required String circleId,
  required CircleMembershipState expected,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  Object? lastError;
  while (DateTime.now().isBefore(deadline)) {
    try {
      final membership = await harness.membershipQueries.getMyMembership(
        MyCircleMembershipQuery(circleId: circleId),
      );
      if (membership.state == expected) return membership;
    } catch (error) {
      lastError = error;
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError(
    'Membership did not converge to ${expected.wireName}; lastError=$lastError',
  );
}

Future<void> _waitForMemberCount(
  CircleApiContractHarness harness, {
  required String circleId,
  required int expected,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  int? lastCount;
  while (DateTime.now().isBefore(deadline)) {
    final circle = await harness.query.get(
      CircleDetailQuery(circleId: circleId),
    );
    lastCount = circle.memberCount;
    if (lastCount == expected) return;
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError(
    'Circle memberCount did not converge: expected=$expected actual=$lastCount',
  );
}

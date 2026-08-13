// readiness_case: conversation_membership_group_admins_app_uat
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-002
/// 两个 disposable actor 先经公开 User command 形成真实互关，再由公开 Chat command
/// 创建私建群与成员事实。production App 只在管理员命令及完整 Remote roster 回读收敛后
/// 离开页面，随后 API 与页面重入共同确认唯一 admin 角色。
///
/// 当前 Gamma 尚无受治理的普通成员越权、人数上限、版本冲突、selective failure 与
/// 同一 candidate Android+iPhone ResultBundle，因此本 runner 不登记 readiness_case。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_admins_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _disposableActorsConfirmed = bool.fromEnvironment(
  'QWQ_CHAT_MEMBERSHIP_DISPOSABLE_ACTORS_ACK',
);

void main() {
  patrolTest(
    'chat_remote_owner_assigns_group_admin_after_authoritative_readback',
    tags: const ['user-acceptance', 'chat', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      ChatApiContractHarness? ownerHarness;
      ChatApiContractHarness? memberHarness;
      UserApiContractHarness? relationshipHarness;

      try {
        ownerHarness = await ChatApiContractHarness.create();
        memberHarness = await ChatApiContractHarness.create();
        relationshipHarness = await UserApiContractHarness.create();
        final owner = ownerHarness.session;
        final member = memberHarness.session;
        final ownerPersonaId = owner.activePersona?.personaId.trim() ?? '';
        final memberPersonaId = member.activePersona?.personaId.trim() ?? '';
        if (ownerPersonaId.isEmpty || memberPersonaId.isEmpty) {
          throw StateError('Disposable Chat actors require active personas');
        }

        await _followAndReadBack(
          relationshipHarness,
          actor: owner,
          targetPersonaId: memberPersonaId,
          idempotencyKey: 'chat-owner-follows-member-$suffix',
        );
        await _followAndReadBack(
          relationshipHarness,
          actor: member,
          targetPersonaId: ownerPersonaId,
          idempotencyKey: 'chat-member-follows-owner-$suffix',
        );

        final conversationId = await ownerHarness.seedConversation();
        await ownerHarness.repository.addMembers(
          conversationId: conversationId,
          userIds: <String>[memberPersonaId],
        );
        final memberRow = await _waitForMember(
          ownerHarness,
          conversationId: conversationId,
          memberPersonaId: memberPersonaId,
          expectedRole: 'member',
        );

        installPatrolAcceptanceSessionForRunner(
          accessToken: owner.accessToken,
          refreshToken: owner.refreshToken,
          ownerId: owner.ownerId,
          personaId: ownerPersonaId,
        );
        await launchPatrolAppOnce($);
        await patrolGoTo($, AppRoutePaths.chatAdmins(id: conversationId));
        await $(find.byType(GroupAdminsPage)).waitUntilVisible();
        await _waitForTextOrFail($, memberRow.displayName);
        await $(find.text(memberRow.displayName)).tap();
        await $.pump(const Duration(milliseconds: 200));
        expect(
          find.byKey(ValueKey<String>('chip_$memberPersonaId')),
          findsOneWidget,
        );
        await $(find.byType(AppNavigationBarTextAction)).tap();
        await _waitForPageDismissal($);

        await _waitForMember(
          ownerHarness,
          conversationId: conversationId,
          memberPersonaId: memberPersonaId,
          expectedRole: 'admin',
        );
        await patrolGoTo($, AppRoutePaths.chatAdmins(id: conversationId));
        await $(find.byType(GroupAdminsPage)).waitUntilVisible();
        await _waitForKeyOrFail($, ValueKey<String>('chip_$memberPersonaId'));
        expect(find.byType(AppPageErrorState), findsNothing);
      } finally {
        try {
          await relationshipHarness?.close();
        } finally {
          try {
            await memberHarness?.close();
          } finally {
            await ownerHarness?.close();
          }
        }
      }
    },
  );
}

Future<void> _followAndReadBack(
  UserApiContractHarness harness, {
  required AuthSessionGrant actor,
  required String targetPersonaId,
  required String idempotencyKey,
}) async {
  await harness.withSession(
    session: actor,
    action: () => harness.withIdempotencyKey(
      idempotencyKey: idempotencyKey,
      action: () => harness.personaRelationshipFollows.follow(
        targetPersonaId,
        sourceSurfaceId: AppUiSurfaces.userProfile.id,
      ),
    ),
  );
  final capability = await harness.withSession(
    session: actor,
    action: () => harness.personaRelationships.getRelationshipCapability(
      GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
    ),
  );
  if (capability.relationState != RelationshipState.following &&
      capability.relationState != RelationshipState.mutual) {
    throw StateError('FollowUser did not converge before Chat membership');
  }
}

Future<ConversationMemberListRow> _waitForMember(
  ChatApiContractHarness harness, {
  required String conversationId,
  required String memberPersonaId,
  required String expectedRole,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    final members = await harness.repository.listMembers(
      conversationId: conversationId,
      limit: 200,
      sort: MemberListSort.joinedAsc,
    );
    for (final member in members) {
      if (member.userId == memberPersonaId && member.role == expectedRole) {
        if (member.displayName.trim().isEmpty) {
          throw StateError('ListMembers returned an empty displayName');
        }
        return member;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('Chat member role did not converge to $expectedRole');
}

Future<void> _waitForTextOrFail(PatrolIntegrationTester $, String text) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production GroupAdmins entered an error terminal');
    }
    if (find.text(text).evaluate().isNotEmpty) return;
    await $.pump(const Duration(milliseconds: 200));
  }
  fail('production GroupAdmins did not render the Remote member');
}

Future<void> _waitForKeyOrFail(PatrolIntegrationTester $, Key key) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production GroupAdmins reentry entered an error terminal');
    }
    if (find.byKey(key).evaluate().isNotEmpty) return;
    await $.pump(const Duration(milliseconds: 200));
  }
  fail('production GroupAdmins did not restore the Remote admin selection');
}

Future<void> _waitForPageDismissal(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(GroupAdminsPage).evaluate().isEmpty) return;
    await $.pump(const Duration(milliseconds: 200));
  }
  fail('GroupAdmins did not dismiss after authoritative Remote readback');
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Chat membership UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('Chat membership UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError('Chat membership UAT requires absolute HTTPS gateways');
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('Chat membership UAT requires one App/API gateway');
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_CHAT_MEMBERSHIP_DISPOSABLE_ACTORS_ACK=true only when account '
      'closure cleanup is permitted',
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

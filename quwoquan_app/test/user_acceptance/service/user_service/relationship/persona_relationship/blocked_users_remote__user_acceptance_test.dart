// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-003
/// Patrol UAT 前置：真实 disposable actor 建立 block edge，并由屏蔽列表分页读回后解除。
///
/// 该 runner 只覆盖真实成功/权威读回路径；Gamma 尚无受治理的 selective failure
/// orchestration，因此不登记 readiness_case，也不冒充完整 GWT-003 商用证据。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_shell.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/blocked_users_page.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _targetUserHandle = String.fromEnvironment(
  'QWQ_PERSONA_RELATIONSHIP_TARGET_USER_HANDLE',
);
const _targetPersonaId = String.fromEnvironment(
  'QWQ_PERSONA_RELATIONSHIP_TARGET_PERSONA_ID',
);
const _disposableActorsConfirmed = bool.fromEnvironment(
  'QWQ_PERSONA_RELATIONSHIP_DISPOSABLE_ACTORS_ACK',
);

void main() {
  patrolTest(
    'blocked_users_remote_block_readback_unblock_and_reopen',
    tags: const ['user-acceptance', 'user', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      try {
        await _openBlockedUsers($);
        await _unblockTargetIfPresent($);

        await patrolGoTo(
          $,
          AppRoutePaths.userProfile(userHandle: _targetUserHandle),
        );
        await $(
          find.byType(ProfileShell),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));
        await $(find.byIcon(CupertinoIcons.ellipsis)).tap();
        await $(find.text(ContentText.profileBlockUser)).waitUntilVisible();
        await $(find.text(ContentText.profileBlockUser)).tap();
        await $.pump(const Duration(milliseconds: 300));
        await $(find.text(ContentText.profileBlockUser)).waitUntilVisible();
        await $(find.text(ContentText.profileBlockUser)).tap();
        await $(
          find.text(ContentText.profileBlockSuccess),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));

        await _openBlockedUsers($);
        await _findTargetAcrossPages($);
        expect(
          _targetHandleFinder(),
          findsOneWidget,
          reason: 'BlockUser 成功后 production Remote 屏蔽列表必须读回目标',
        );

        await _unblockTargetIfPresent($);
        expect(_targetHandleFinder(), findsNothing);

        await patrolGoTo($, AppRoutePaths.home);
        await _openBlockedUsers($);
        await _findTargetAcrossPages($);
        expect(
          _targetHandleFinder(),
          findsNothing,
          reason: '重入页面后 production Remote 必须确认目标仍已解除屏蔽',
        );
      } finally {
        await _openBlockedUsers($);
        await _unblockTargetIfPresent($);
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'PersonaRelationship UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'PersonaRelationship UAT requires an injected authenticated actor; '
      'anonymous Patrol sessions are not evidence',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError(
      'PersonaRelationship UAT requires an absolute HTTPS gateway',
    );
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_PERSONA_RELATIONSHIP_DISPOSABLE_ACTORS_ACK=true only for '
      'two disposable production actors',
    );
  }
  if (_targetUserHandle.trim().isEmpty || _targetPersonaId.trim().isEmpty) {
    throw StateError(
      'PersonaRelationship UAT requires target handle and personaId',
    );
  }
  if (_targetPersonaId.trim() == kPatrolAcceptanceCurrentPersonaId.trim()) {
    throw StateError('PersonaRelationship target must differ from viewer');
  }
}

Future<void> _openBlockedUsers(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.blockedUsers);
  await $(
    find.byType(BlockedUsersPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await _waitForBlockedListTerminal($);
}

Future<void> _waitForBlockedListTerminal(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoRelationshipFailure();
    if (_targetHandleFinder().evaluate().isNotEmpty ||
        find.text(ContentText.blockedUsersEmptyTitle).evaluate().isNotEmpty ||
        find.text(ContentText.blockedUsersUnblock).evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('屏蔽列表未从 production Remote 到达可用终态');
}

Future<void> _findTargetAcrossPages(PatrolIntegrationTester $) async {
  await _waitForBlockedListTerminal($);
  while (_targetHandleFinder().evaluate().isEmpty &&
      find.text(ContentText.loadMore).evaluate().isNotEmpty) {
    await $(find.text(ContentText.loadMore)).tap();
    await $.pump(const Duration(milliseconds: 500));
    _expectNoRelationshipFailure();
  }
}

Future<void> _unblockTargetIfPresent(PatrolIntegrationTester $) async {
  await _findTargetAcrossPages($);
  final handle = _targetHandleFinder();
  if (handle.evaluate().isEmpty) {
    return;
  }
  final row = find.ancestor(of: handle, matching: find.byType(Row));
  final unblock = find.descendant(
    of: row,
    matching: find.text(ContentText.blockedUsersUnblock),
  );
  await $(unblock).tap();
  final confirmation = find.descendant(
    of: find.byType(CupertinoAlertDialog),
    matching: find.text(ContentText.blockedUsersUnblock),
  );
  await $(confirmation).waitUntilVisible();
  await $(confirmation).tap();

  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoRelationshipFailure();
    if (handle.evaluate().isEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('UnblockUser 未在 production Remote 权威读回后移除目标');
}

Finder _targetHandleFinder() => find.text('@${_targetUserHandle.trim()}');

void _expectNoRelationshipFailure() {
  expect(
    find.byType(AppPageErrorState),
    findsNothing,
    reason: 'PersonaRelationship Remote failure cannot masquerade as success',
  );
  expect(
    find.byType(CupertinoAlertDialog),
    findsNothing,
    reason: 'Unexpected relationship dialog blocks the UAT journey',
  );
}

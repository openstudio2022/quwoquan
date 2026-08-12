// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-003
/// Patrol UAT 前置由公开 User API 创建两个 disposable actor 与真实 block edge。
///
/// 该 runner 只覆盖成功路径与权威读回；Gamma 尚无受治理的 selective failure
/// orchestration，因此不登记 readiness_case，也不冒充完整 GWT-003 商用证据。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/blocked_users_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';
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
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final viewerHarness = await UserApiContractHarness.create();
      UserApiContractHarness? targetHarness;
      AuthSessionGrant? viewer;
      AuthSessionGrant? target;

      try {
        targetHarness = await UserApiContractHarness.create();
        viewer = await viewerHarness.loginDisposableAccount(
          'blocked-users-viewer-$suffix',
        );
        target = await targetHarness.loginDisposableAccount(
          'blocked-users-target-$suffix',
        );
        final viewerPersonaId = viewer.activePersona?.personaId.trim() ?? '';
        final targetPersonaId = target.activePersona?.personaId.trim() ?? '';
        if (viewerPersonaId.isEmpty || targetPersonaId.isEmpty) {
          throw StateError('Disposable accounts require active personas');
        }

        final blockResult = await viewerHarness.personaRelationships.blockUser(
          BlockUserCommand(targetPersonaId: targetPersonaId),
        );
        if (!blockResult.blocked ||
            blockResult.targetPersonaId != targetPersonaId) {
          throw StateError('BlockUser returned a mismatched typed result');
        }
        final targetHandle = await _readBlockedTargetHandle(
          viewerHarness,
          targetPersonaId,
        );

        installPatrolAcceptanceSessionForRunner(
          accessToken: viewer.accessToken,
          refreshToken: viewer.refreshToken,
          ownerId: viewer.ownerId,
          personaId: viewerPersonaId,
        );
        await launchPatrolAppOnce($);

        await _openBlockedUsers($);
        await _findTargetAcrossPages($, targetHandle);
        expect(
          _targetHandleFinder(targetHandle),
          findsOneWidget,
          reason: '真实 BlockUser 前置必须由 production Remote 列表读回',
        );

        await _unblockTarget($, targetHandle);
        expect(_targetHandleFinder(targetHandle), findsNothing);

        await patrolGoTo($, AppRoutePaths.home);
        await _openBlockedUsers($);
        await _findTargetAcrossPages($, targetHandle);
        expect(
          _targetHandleFinder(targetHandle),
          findsNothing,
          reason: '重入页面后 production Remote 必须确认目标仍已解除屏蔽',
        );
      } finally {
        try {
          if (target != null && targetHarness != null) {
            await targetHarness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'blocked-users-target-cleanup-$suffix',
              ),
            );
          }
        } finally {
          try {
            if (viewer != null) {
              await viewerHarness.accountLifecycle.closeAccount(
                CloseAccountCommand(
                  clientRequestId: 'blocked-users-viewer-cleanup-$suffix',
                ),
              );
            }
          } finally {
            try {
              await targetHarness?.close();
            } finally {
              await viewerHarness.close();
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
      'PersonaRelationship UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'PersonaRelationship UAT installs its own disposable viewer session',
    );
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'PersonaRelationship UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'PersonaRelationship UAT requires App and API to use the same gateway',
    );
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_PERSONA_RELATIONSHIP_DISPOSABLE_ACTORS_ACK=true only when '
      'public CloseAccount cleanup is permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null && value.isAbsolute && value.scheme == 'https' && value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}

Future<String> _readBlockedTargetHandle(
  UserApiContractHarness harness,
  String targetPersonaId,
) async {
  String? cursor;
  final seenCursors = <String>{};
  do {
    final page = await harness.personaRelationships.listBlockedUsers(
      ListBlockedUsersQuery(cursor: cursor, limit: 100),
    );
    for (final item in page.items) {
      if (item.targetPersonaId == targetPersonaId) {
        final handle = item.userHandle.trim();
        if (handle.isEmpty) {
          throw StateError('Blocked target returned an empty userHandle');
        }
        return handle;
      }
    }
    cursor = page.nextCursor?.trim();
    if (cursor != null && cursor.isNotEmpty && !seenCursors.add(cursor)) {
      throw StateError('ListBlockedUsers returned a cursor cycle');
    }
  } while (cursor != null && cursor.isNotEmpty);
  throw StateError('BlockUser target is absent from authoritative readback');
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
    if (find.text(ContentText.blockedUsersEmptyTitle).evaluate().isNotEmpty ||
        find.text(ContentText.blockedUsersUnblock).evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('屏蔽列表未从 production Remote 到达可用终态');
}

Future<void> _findTargetAcrossPages(
  PatrolIntegrationTester $,
  String targetHandle,
) async {
  await _waitForBlockedListTerminal($);
  while (_targetHandleFinder(targetHandle).evaluate().isEmpty &&
      find.text(ContentText.loadMore).evaluate().isNotEmpty) {
    await $(find.text(ContentText.loadMore)).tap();
    await $.pump(const Duration(milliseconds: 500));
    _expectNoRelationshipFailure();
  }
}

Future<void> _unblockTarget(
  PatrolIntegrationTester $,
  String targetHandle,
) async {
  await _findTargetAcrossPages($, targetHandle);
  final handle = _targetHandleFinder(targetHandle);
  expect(handle, findsOneWidget);
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

Finder _targetHandleFinder(String handle) => find.text('@${handle.trim()}');

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

// readiness_case: greeting_request_inbox_app_uat
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-004
/// 两个 disposable actor 经公开 User API 建立真实 GreetingRequest，随后由
/// production App 完成回复升级、忽略、撤回与 Remote 权威读回。
///
/// 页面已对 reply/ignore/cancel 保留 caller-bound 同意图重放；当前 Gamma 仍没有
/// 受治理的 selective failure orchestration，因此本 runner 不登记 readiness_case。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/presentation/greeting_inbox_page.dart';
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
  'QWQ_GREETING_REQUEST_DISPOSABLE_ACTORS_ACK',
);

void main() {
  patrolTest(
    'greeting_request_remote_reply_ignore_cancel_and_readback',
    tags: const ['user-acceptance', 'user', 'chat', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final viewerHarness = await UserApiContractHarness.create();
      UserApiContractHarness? peerHarness;
      AuthSessionGrant? viewer;
      AuthSessionGrant? peer;

      try {
        peerHarness = await UserApiContractHarness.create();
        viewer = await viewerHarness.loginDisposableAccount(
          'greeting-viewer-$suffix',
        );
        peer = await peerHarness.loginDisposableAccount(
          'greeting-peer-$suffix',
        );
        final viewerPersonaId = viewer.activePersona?.personaId.trim() ?? '';
        final peerPersonaId = peer.activePersona?.personaId.trim() ?? '';
        if (viewerPersonaId.isEmpty || peerPersonaId.isEmpty) {
          throw StateError('Disposable accounts require active personas');
        }

        final relationshipBefore = await viewerHarness.personaRelationships
            .getRelationshipCapability(
              GetRelationshipCapabilityQuery(targetPersonaId: peerPersonaId),
            );
        if (relationshipBefore.relationState !=
            RelationshipState.notFollowing) {
          throw StateError('Greeting UAT requires non-following actors');
        }

        final replyMessage = 'greeting-reply-$suffix';
        final replyRequest = await _sendGreeting(
          peerHarness,
          targetPersonaId: viewerPersonaId,
          message: replyMessage,
          idempotencyKey: 'greeting-reply-setup-$suffix',
        );

        installPatrolAcceptanceSessionForRunner(
          accessToken: viewer.accessToken,
          refreshToken: viewer.refreshToken,
          ownerId: viewer.ownerId,
          personaId: viewerPersonaId,
        );
        await launchPatrolAppOnce($);
        await _openGreetingInbox($);
        await $(find.text(replyMessage)).waitUntilVisible();
        await $(find.text(ChatText.chatGreetingInboxReply)).tap();
        await _waitForGreetingPageToClose($);

        final replied = await _findRemoteRequest(
          viewerHarness,
          requestId: replyRequest.id,
          inbox: true,
        );
        if (replied.status != GreetingRequestStatus.replied ||
            (replied.promotedConversationId?.trim().isEmpty ?? true)) {
          throw StateError('Reply did not converge to one formal conversation');
        }
        await _openGreetingInbox($);
        await $(find.text(replyMessage)).waitUntilVisible();
        expect(
          find.text(ChatText.chatGreetingStatusReplied),
          findsOneWidget,
        );

        final ignoreMessage = 'greeting-ignore-$suffix';
        final ignoreRequest = await _sendGreeting(
          peerHarness,
          targetPersonaId: viewerPersonaId,
          message: ignoreMessage,
          idempotencyKey: 'greeting-ignore-setup-$suffix',
        );
        await _reopenGreetingInbox($);
        await $(find.text(ignoreMessage)).waitUntilVisible();
        await $(find.text(ChatText.chatGreetingInboxIgnore)).tap();
        await $(find.text(ChatText.chatGreetingIgnored)).waitUntilVisible();
        final ignored = await _findRemoteRequest(
          viewerHarness,
          requestId: ignoreRequest.id,
          inbox: true,
        );
        if (ignored.status != GreetingRequestStatus.ignored ||
            ignored.promotedConversationId != null) {
          throw StateError('Ignore returned a non-canonical terminal record');
        }
        await _reopenGreetingInbox($);
        await $(find.text(ignoreMessage)).waitUntilVisible();
        expect(
          find.text(ChatText.chatGreetingStatusIgnored),
          findsOneWidget,
        );

        final cancelMessage = 'greeting-cancel-$suffix';
        final cancelRequest = await _sendGreeting(
          viewerHarness,
          targetPersonaId: peerPersonaId,
          message: cancelMessage,
          idempotencyKey: 'greeting-cancel-setup-$suffix',
        );
        await _reopenGreetingInbox($);
        await $(find.text(ChatText.chatGreetingSentTab)).tap();
        await $(find.text(cancelMessage)).waitUntilVisible();
        await $(find.text(ChatText.chatGreetingCancel)).tap();
        await $(find.text(ChatText.chatGreetingCancel).last).tap();
        await $(find.text(ChatText.chatGreetingCancelled)).waitUntilVisible();
        final cancelled = await _findRemoteRequest(
          viewerHarness,
          requestId: cancelRequest.id,
          inbox: false,
        );
        if (cancelled.status != GreetingRequestStatus.cancelled ||
            cancelled.promotedConversationId != null) {
          throw StateError('Cancel returned a non-canonical terminal record');
        }
        await _reopenGreetingInbox($);
        await $(find.text(ChatText.chatGreetingSentTab)).tap();
        await $(find.text(cancelMessage)).waitUntilVisible();
        expect(
          find.text(ChatText.chatGreetingStatusCancelled),
          findsOneWidget,
        );

        final relationshipAfter = await viewerHarness.personaRelationships
            .getRelationshipCapability(
              GetRelationshipCapabilityQuery(targetPersonaId: peerPersonaId),
            );
        if (relationshipAfter.relationState !=
            RelationshipState.notFollowing) {
          throw StateError('Greeting transitions must not create a follow edge');
        }
      } finally {
        try {
          if (peer != null && peerHarness != null) {
            await peerHarness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'greeting-peer-cleanup-$suffix',
              ),
            );
          }
        } finally {
          try {
            if (viewer != null) {
              await viewerHarness.accountLifecycle.closeAccount(
                CloseAccountCommand(
                  clientRequestId: 'greeting-viewer-cleanup-$suffix',
                ),
              );
            }
          } finally {
            try {
              await peerHarness?.close();
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
      'GreetingRequest UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('GreetingRequest UAT installs its own viewer session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'GreetingRequest UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'GreetingRequest UAT requires App and API to use the same gateway',
    );
  }
  if (!_disposableActorsConfirmed) {
    throw StateError(
      'Set QWQ_GREETING_REQUEST_DISPOSABLE_ACTORS_ACK=true only when public '
      'CloseAccount cleanup is permitted',
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

Future<GreetingRequestRecord> _sendGreeting(
  UserApiContractHarness harness, {
  required String targetPersonaId,
  required String message,
  required String idempotencyKey,
}) {
  return harness.withIdempotencyKey(
    idempotencyKey: idempotencyKey,
    action: () => harness.greetingRequests.sendGreeting(
      SendGreetingCommand(
        targetPersonaId: targetPersonaId,
        requestMessage: message,
        source: 'profile',
      ),
    ),
  );
}

Future<GreetingRequestRecord> _findRemoteRequest(
  UserApiContractHarness harness, {
  required String requestId,
  required bool inbox,
}) async {
  String? cursor;
  final seenCursors = <String>{};
  do {
    final page = inbox
        ? await harness.greetingRequests.listGreetingInbox(
            ListGreetingRequestsQuery(status: '', cursor: cursor, limit: 100),
          )
        : await harness.greetingRequests.listGreetingOutbox(
            ListGreetingRequestsQuery(status: '', cursor: cursor, limit: 100),
          );
    for (final item in page.items) {
      if (item.id == requestId) {
        return item;
      }
    }
    cursor = page.nextCursor?.trim();
    if (cursor != null && cursor.isNotEmpty && !seenCursors.add(cursor)) {
      throw StateError('GreetingRequest readback returned a cursor cycle');
    }
  } while (cursor != null && cursor.isNotEmpty);
  throw StateError('GreetingRequest $requestId is absent from Remote readback');
}

Future<void> _openGreetingInbox(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.greetingInbox);
  await $(
    find.byType(GreetingInboxPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await _waitForGreetingTerminal($);
}

Future<void> _reopenGreetingInbox(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.home);
  await _openGreetingInbox($);
}

Future<void> _waitForGreetingTerminal(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoFailure();
    if (find.text(ChatText.chatGreetingReceived).evaluate().isNotEmpty &&
        find.text(ChatText.chatGreetingSentTab).evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('Greeting inbox did not reach a production Remote terminal state');
}

Future<void> _waitForGreetingPageToClose(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoFailure();
    if (find.byType(GreetingInboxPage).evaluate().isEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('ReplyGreetingRequest did not navigate to its promoted conversation');
}

void _expectNoFailure() {
  expect(
    find.byType(AppPageErrorState),
    findsNothing,
    reason: 'GreetingRequest Remote failure cannot masquerade as success',
  );
  expect(
    find.byType(CupertinoAlertDialog),
    findsNothing,
    reason: 'Unexpected GreetingRequest dialog blocks the UAT journey',
  );
}

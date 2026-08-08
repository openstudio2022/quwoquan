// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
// readiness_case: user_account_close_account_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

const String _idempotencyKey = 'close-account-request-1';
const String _closedAt = '2026-08-08T12:00:00Z';

void main() {
  test(
    'CloseAccount exact POST wire, stable replay and typed terminal result',
    () async {
      final log = <CapturedRemoteApiPathRequest>[];
      var attempt = 0;
      final writer = _buildWriter(
        log,
        responseFor: (_) {
          final replay = attempt > 0;
          attempt += 1;
          return remoteApiPathJsonResponse(<String, Object?>{
            'accountState': 'closed',
            'closedAt': _closedAt,
            'idempotentReplay': replay,
          });
        },
      );
      const command = CloseAccountCommand(clientRequestId: _idempotencyKey);

      final first = await writer.closeAccount(command);
      final replay = await writer.closeAccount(command);

      expect(first.accountState, AccountState.closed);
      expect(first.idempotentReplay, isFalse);
      expect(replay.accountState, AccountState.closed);
      expect(replay.idempotentReplay, isTrue);
      expect(replay.closedAt, first.closedAt);
      expect(log, hasLength(2));
      for (final request in log) {
        expect(request.method, 'POST');
        expect(
          request.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountCloseAccount,
          ),
        );
        expect(request.query, isEmpty);
        expect(request.body, <String, Object?>{
          'clientRequestId': _idempotencyKey,
        });
        expect(request.headers['Idempotency-Key'], _idempotencyKey);
        expect(
          request.headers['Authorization'],
          'Bearer integration-contract-token',
        );
        expectRemoteApiPathHeaders(
          request.headers,
          clientPageId: UserRequestPageIds.closeAccount,
          surfaceId: _closeAccountSurface.id,
          operationId: AppCloudOperationIds.userUserAccountCloseAccount,
        );
      }
    },
  );

  test(
    'CloseAccount canonical failure is not converted to a closed result',
    () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final writer = _buildWriter(
        log,
        responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
          'code': 'USER.SYSTEM.internal_error',
          'message': 'account closure unavailable',
        }, statusCode: 503),
      );

      await expectLater(
        writer.closeAccount(
          const CloseAccountCommand(clientRequestId: _idempotencyKey),
        ),
        throwsA(isA<CloudException>()),
      );
      expect(log, isNotEmpty);
      expect(log.last.headers['Idempotency-Key'], _idempotencyKey);
      expect(
        log.last.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.userUserAccountCloseAccount,
      );
    },
  );
}

RemoteAccountLifecycleCommandWriter _buildWriter(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  return RemoteAccountLifecycleCommandWriter(
    client: buildRemoteApiPathOperationClient(log, responseFor: responseFor),
    invocationContext: (clientPageId) => CloudOperationInvocationContext(
      surfaceId: _closeAccountSurface.id,
      routeId: _closeAccountSurface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: _idempotencyKey,
      actor: const CloudOperationActorContext(
        accountId: 'owner-1',
        personaId: 'persona-1',
      ),
    ),
  );
}

AppUiSurface get _closeAccountSurface {
  final operation =
      appCloudOperationContracts[AppCloudOperationIds
          .userUserAccountCloseAccount]!;
  return AppUiSurfaces.byId[operation.surfaceIds.first]!;
}

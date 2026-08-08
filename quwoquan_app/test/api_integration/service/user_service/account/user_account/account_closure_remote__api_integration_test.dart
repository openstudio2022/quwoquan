// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
// readiness_case: user_account_close_account_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  UserApiContractHarness? harness;

  UserApiContractHarness activeHarness() {
    return harness ??
        (throw StateError('UserApiContractHarness setup did not complete'));
  }

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() async {
    await harness?.close();
  });

  test(
    'CloseAccount retains exact generated POST body/idempotency contract',
    () {
      final contract =
          appCloudOperationContracts[AppCloudOperationIds
              .userUserAccountCloseAccount];
      expect(contract, isNotNull);
      expect(contract!.objectId, 'user.user_account');
      expect(contract.method, 'POST');
      expect(contract.pathTemplate, '/owner/account/close');
      expect(contract.requestBodyKind, 'object');
      expect(contract.requestPathBindings, isEmpty);
      expect(contract.requestQueryBindings, isEmpty);
      expect(contract.idempotency, 'required');
    },
  );

  test(
    'CloseAccount returns a stable terminal state and exact telemetry',
    () async {
      final api = activeHarness();
      await api.loginDisposableAccount('close');
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final idempotencyKey = 'user-account-close-$nonce';
      final command = CloseAccountCommand(clientRequestId: 'close-$nonce');

      final result = await api.withIdempotencyKey(
        idempotencyKey: idempotencyKey,
        action: () => api.accountLifecycle.closeAccount(command),
      );
      final replay = await api.withIdempotencyKey(
        idempotencyKey: idempotencyKey,
        action: () => api.accountLifecycle.closeAccount(command),
      );

      expect(result.accountState, AccountState.closed);
      expect(result.closedAt.isUtc, isTrue);
      expect(result.idempotentReplay, isFalse);
      expect(replay.accountState, AccountState.closed);
      expect(replay.closedAt, result.closedAt);
      expect(replay.idempotentReplay, isTrue);

      final contract =
          appCloudOperationContracts[AppCloudOperationIds
              .userUserAccountCloseAccount]!;
      await expectLater(
        api.withTemporaryAccessToken(
          accessToken: 'invalid-user-account-api-contract-token',
          action: () => api.withIdempotencyKey(
            idempotencyKey: 'user-account-close-invalid-$nonce',
            action: () => api.accountLifecycle.closeAccount(
              CloseAccountCommand(clientRequestId: 'close-invalid-$nonce'),
            ),
          ),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.userUserAccountCloseAccount,
              )
              .having(
                (error) => error.statusCode,
                'statusCode',
                anyOf(401, 403),
              )
              .having(
                (error) => error.code,
                'canonical code',
                isIn(contract.errorCodes),
              ),
        ),
      );

      final telemetryEvents = await api.telemetry.waitForEvents(
        minimumCount: 1,
      );
      final closeEvents = telemetryEvents.where(
        (event) =>
            event.canonicalOperationId ==
            AppCloudOperationIds.userUserAccountCloseAccount,
      );
      expect(
        closeEvents
            .where(
              (event) =>
                  event.succeeded &&
                  event.statusCode == 200 &&
                  event.requestId.isNotEmpty &&
                  event.traceId.isNotEmpty,
            )
            .length,
        greaterThanOrEqualTo(2),
      );
      expect(
        closeEvents.any(
          (event) =>
              !event.succeeded &&
              (event.statusCode == 401 || event.statusCode == 403) &&
              event.requestId.isNotEmpty &&
              event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}

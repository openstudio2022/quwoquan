// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001.t2
// readiness_case: device_registration_upsert_device_push_endpoint_app_api
// readiness_case: device_registration_remove_device_push_endpoint_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() => harness.close());

  test('production Remote 通过真实 gateway 幂等注册、移除并拒绝无效 bearer', () async {
    final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    await harness.loginDisposableAccount('device-registration-$suffix');
    final endpoint = DevicePushEndpoint(
      kind: PushEndpointKind.fcm,
      token: 'device-registration-api-$suffix',
    );
    var registered = false;
    var removed = false;
    var accountClosed = false;
    addTearDown(() async {
      try {
        if (registered && !removed) {
          await harness.devicePushEndpoints.remove(endpoint);
        }
      } finally {
        if (!accountClosed) {
          await harness.accountLifecycle.closeAccount(
            CloseAccountCommand(
              clientRequestId: 'device-registration-cleanup-$suffix',
            ),
          );
        }
      }
    });

    await harness.devicePushEndpoints.upsert(endpoint);
    registered = true;
    await harness.devicePushEndpoints.upsert(endpoint);

    await expectLater(
      harness.withTemporaryAccessToken<void>(
        accessToken: 'invalid-device-registration-api-token',
        action: () => harness.devicePushEndpoints.upsert(endpoint),
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          anyOf(401, 403),
        ),
      ),
    );

    await harness.devicePushEndpoints.remove(endpoint);
    await harness.devicePushEndpoints.remove(endpoint);
    removed = true;

    final events = await harness.telemetry.waitForEvents(minimumCount: 6);
    final endpointEvents = events
        .where(
          (event) =>
              event.canonicalOperationId ==
                  AppCloudOperationIds
                      .userDeviceRegistrationUpsertDevicePushEndpoint ||
              event.canonicalOperationId ==
                  AppCloudOperationIds
                      .userDeviceRegistrationRemoveDevicePushEndpoint,
        )
        .toList(growable: false);

    expect(endpointEvents.map((event) => event.canonicalOperationId), <String>[
      AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
      AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
      AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
      AppCloudOperationIds.userDeviceRegistrationRemoveDevicePushEndpoint,
      AppCloudOperationIds.userDeviceRegistrationRemoveDevicePushEndpoint,
    ]);
    expect(endpointEvents.where((event) => event.succeeded), hasLength(4));
    expect(
      endpointEvents.where((event) => !event.succeeded).single.statusCode,
      anyOf(401, 403),
    );
    expect(
      endpointEvents.every(
        (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
      ),
      isTrue,
    );

    await harness.accountLifecycle.closeAccount(
      CloseAccountCommand(
        clientRequestId: 'device-registration-cleanup-$suffix',
      ),
    );
    accountClosed = true;
  });
}

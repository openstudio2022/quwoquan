// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001.t2
// readiness_case: device_registration_upsert_device_push_endpoint_app_local
// readiness_case: device_registration_remove_device_push_endpoint_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/service/user_service/account/device_registration/adapters/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/service/user_service/account/device_registration/application/device_push_endpoint_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'Push endpoint upsert/remove 只走 canonical generated operation',
    () async {
      final executor = _DeviceRegistrationExecutor();
      final writer = RemoteDevicePushEndpointWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'runtime.push-endpoint',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            deviceActorId: 'device-1',
          ),
        ),
        clientContextSnapshot: () => const CloudClientContextSnapshot(
          sessionId: 'session-1',
          platform: 'android',
          appVersion: '1.2.3',
          locale: 'zh-CN',
          deviceActorId: 'device-1',
        ),
      );
      final endpoint = DevicePushEndpoint(
        kind: PushEndpointKind.fcm,
        token: 'fcm-registration-token',
      );

      await writer.upsert(endpoint);
      await writer.remove(endpoint);

      expect(executor.operationIds, <String>[
        AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
        AppCloudOperationIds.userDeviceRegistrationRemoveDevicePushEndpoint,
      ]);
      expect(executor.payloads[0].pathParameters, <String, String>{
        'deviceId': 'device-1',
        'endpointKind': 'fcm',
      });
      expect(executor.payloads[0].body, <String, Object?>{
        'token': 'fcm-registration-token',
        'appVersion': '1.2.3',
      });
      expect(executor.payloads[1].pathParameters, <String, String>{
        'deviceId': 'device-1',
        'endpointKind': 'fcm',
      });
      expect(executor.payloads[1].body, isNull);
    },
  );

  test('缺少可信 device actor 时在 generated client 之前 fail closed', () async {
    final executor = _DeviceRegistrationExecutor();
    final writer = RemoteDevicePushEndpointWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: 'runtime.push-endpoint',
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(accountId: 'account-1'),
      ),
      clientContextSnapshot: () => const CloudClientContextSnapshot(
        sessionId: 'session-1',
        platform: 'android',
        appVersion: '1.2.3',
        locale: 'zh-CN',
      ),
    );

    await expectLater(
      writer.upsert(
        DevicePushEndpoint(kind: PushEndpointKind.fcm, token: 'token'),
      ),
      throwsStateError,
    );
    expect(executor.operationIds, isEmpty);
  });

  test('本地 mutation 仅在 writer 成功后 ack，失败保持待重试', () async {
    final gateway = _RecordingPushEndpointGateway()
      ..pending.addAll(<PushEndpointMutation>[
        PushEndpointMutation(
          mutationId: 'mutation-upsert',
          kind: PushEndpointMutationKind.upsert,
          endpoint: DevicePushEndpoint(
            kind: PushEndpointKind.fcm,
            token: 'token-upsert',
          ),
          occurredAt: DateTime.utc(2026, 8, 8),
        ),
        PushEndpointMutation(
          mutationId: 'mutation-remove',
          kind: PushEndpointMutationKind.remove,
          endpoint: DevicePushEndpoint(
            kind: PushEndpointKind.fcm,
            token: 'token-remove',
          ),
          occurredAt: DateTime.utc(2026, 8, 8, 0, 1),
        ),
      ]);
    final writer = _RecordingDevicePushEndpointWriter(failRemove: true);
    final coordinator = DevicePushEndpointCoordinator(
      gateway: gateway,
      writer: writer,
    );

    await expectLater(coordinator.syncAfterLogin(), throwsStateError);

    expect(writer.upserts.single.token, 'token-upsert');
    expect(writer.removals.single.token, 'token-remove');
    expect(gateway.acknowledged, <String>['mutation-upsert']);
    expect(gateway.pending.map((mutation) => mutation.mutationId), <String>[
      'mutation-remove',
    ]);
  });
}

final class _DeviceRegistrationExecutor implements CloudOperationExecutor {
  final operationIds = <String>[];
  final payloads = <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    payloads.add(requestEncoder());
    return responseDecoder(<String, Object?>{
      'endpointRef': 'device-1:fcm',
      'deviceId': 'device-1',
      'endpointKind': 'fcm',
      'status': 'active',
      'version': 1,
      'aggregateVersion': 1,
      'idempotentReplay': false,
      'updatedAt': '2026-08-08T08:00:00Z',
    });
  }
}

final class _RecordingPushEndpointGateway implements PushEndpointGateway {
  final pending = <PushEndpointMutation>[];
  final acknowledged = <String>[];

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) async {}

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() async =>
      List<PushEndpointMutation>.of(pending);

  @override
  Future<void> acknowledgeMutation(String mutationId) async {
    acknowledged.add(mutationId);
    pending.removeWhere((mutation) => mutation.mutationId == mutationId);
  }

  @override
  Future<void> queueActiveEndpointRemovals() async {}

  @override
  Future<void> purgeForTerminalAccountClosure() async {
    pending.clear();
  }
}

final class _RecordingDevicePushEndpointWriter
    implements DevicePushEndpointWriter {
  _RecordingDevicePushEndpointWriter({required this.failRemove});

  final bool failRemove;
  final upserts = <DevicePushEndpoint>[];
  final removals = <DevicePushEndpoint>[];

  @override
  Future<void> upsert(DevicePushEndpoint endpoint) async {
    upserts.add(endpoint);
  }

  @override
  Future<void> remove(DevicePushEndpoint endpoint) async {
    removals.add(endpoint);
    if (failRemove) {
      throw StateError('remote removal failed');
    }
  }
}

import 'package:quwoquan_app/service/user_service/account/device_registration/application/device_push_endpoint_writer.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef DevicePushInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteDevicePushEndpointWriter implements DevicePushEndpointWriter {
  RemoteDevicePushEndpointWriter({
    required this.client,
    required this.invocationContext,
    required this.clientContextSnapshot,
  });

  final GeneratedCloudOperationClient client;
  final DevicePushInvocationContextFactory invocationContext;
  final CloudClientContextSnapshot Function() clientContextSnapshot;

  @override
  Future<void> upsert(DevicePushEndpoint endpoint) async {
    final snapshot = clientContextSnapshot();
    await client.userDeviceRegistrationUpsertDevicePushEndpoint(
      DevicePushEndpointUpsertCommand(
        deviceId: _deviceId(snapshot),
        endpointKind: _kind(endpoint.kind),
        token: endpoint.token,
        appVersion: snapshot.appVersion,
      ),
      context: invocationContext(UserRequestPageIds.upsertDevicePushEndpoint),
    );
  }

  @override
  Future<void> remove(DevicePushEndpoint endpoint) async {
    final snapshot = clientContextSnapshot();
    await client.userDeviceRegistrationRemoveDevicePushEndpoint(
      DevicePushEndpointRemoveCommand(
        deviceId: _deviceId(snapshot),
        endpointKind: _kind(endpoint.kind),
      ),
      context: invocationContext(UserRequestPageIds.removeDevicePushEndpoint),
    );
  }

  String _deviceId(CloudClientContextSnapshot snapshot) {
    final value = (snapshot.deviceActorId ?? '').trim();
    if (value.isEmpty) {
      throw StateError('device actor id is unavailable');
    }
    return value;
  }

  DevicePushEndpointKind _kind(PushEndpointKind kind) => switch (kind) {
    PushEndpointKind.apnsVoip => DevicePushEndpointKind.apnsVoip,
    PushEndpointKind.fcm => DevicePushEndpointKind.fcm,
  };
}

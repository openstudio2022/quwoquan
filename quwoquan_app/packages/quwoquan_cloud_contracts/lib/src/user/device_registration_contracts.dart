import 'user_operation_contracts.g.dart';

abstract interface class DeviceRegistrationCommandWriter {
  Future<DevicePushEndpointCommandResult> upsertPushEndpoint(
    DevicePushEndpointUpsertCommand command,
  );
  Future<DevicePushEndpointCommandResult> removePushEndpoint(
    DevicePushEndpointRemoveCommand command,
  );
}

// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/device_registration_contracts.dart';

final class DevicePushEndpointRemoveCommand {
  DevicePushEndpointRemoveCommand({
    required String deviceId,
    required DevicePushEndpointKind endpointKind,
  }) : deviceId = deviceId.trim(),
       endpointKind = endpointKind {
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
  }

  final String deviceId;
  final DevicePushEndpointKind endpointKind;
}

final class DevicePushEndpointUpsertCommand {
  DevicePushEndpointUpsertCommand({
    required String deviceId,
    required DevicePushEndpointKind endpointKind,
    required String token,
    required String appVersion,
  }) : deviceId = deviceId.trim(),
       endpointKind = endpointKind,
       token = token.trim(),
       appVersion = appVersion.trim() {
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.token.isEmpty) {
      throw ArgumentError.value(this.token, "token", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(this.appVersion, "appVersion", 'must not be blank');
    }
  }

  final String deviceId;
  final DevicePushEndpointKind endpointKind;
  final String token;
  final String appVersion;
}

CloudOperationRequestPayload encodeUserDeviceRegistrationRemoveDevicePushEndpointGeneratedRequest(DevicePushEndpointRemoveCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "deviceId": request.deviceId,
      "endpointKind": (switch (request.endpointKind) { DevicePushEndpointKind.apnsVoip => "apns_voip", DevicePushEndpointKind.fcm => "fcm", }).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserDeviceRegistrationUpsertDevicePushEndpointGeneratedRequest(DevicePushEndpointUpsertCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "deviceId": request.deviceId,
      "endpointKind": (switch (request.endpointKind) { DevicePushEndpointKind.apnsVoip => "apns_voip", DevicePushEndpointKind.fcm => "fcm", }).toString(),
    },
    body: <String, Object?>{
      "token": request.token,
      "appVersion": request.appVersion,
    },
  );
}


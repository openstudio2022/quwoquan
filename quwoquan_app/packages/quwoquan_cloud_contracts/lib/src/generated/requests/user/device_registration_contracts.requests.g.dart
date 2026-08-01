// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "deviceId": this.deviceId,
    "endpointKind": switch (this.endpointKind) { DevicePushEndpointKind.apnsVoip => "apns_voip", DevicePushEndpointKind.fcm => "fcm", },
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "deviceId": this.deviceId,
    "endpointKind": switch (this.endpointKind) { DevicePushEndpointKind.apnsVoip => "apns_voip", DevicePushEndpointKind.fcm => "fcm", },
    "token": this.token,
    "appVersion": this.appVersion,
  };
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


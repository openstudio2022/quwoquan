// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/authentication_challenge_contracts.dart';

final class CreateAlipayAuthorizationRequestCommand {
  const CreateAlipayAuthorizationRequestCommand({
    String? platform,
    String? appVersion,
  }) : platform = platform,
       appVersion = appVersion;

  final String? platform;
  final String? appVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.platform != null) "platform": this.platform!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
  };
}

final class ResolveOneTapLoginHintCommand {
  ResolveOneTapLoginHintCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion {
    if (this.vendor.isEmpty) {
      throw ArgumentError.value(this.vendor, "vendor", 'must not be blank');
    }
    if (this.carrierToken.isEmpty) {
      throw ArgumentError.value(this.carrierToken, "carrierToken", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
  }

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? appVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
  };
}

final class SendOtpCommand {
  SendOtpCommand({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
    String? bindingTicket,
  }) : phone = phone.trim(),
       deviceId = deviceId,
       platform = platform,
       appVersion = appVersion,
       sourceOperation = sourceOperation,
       bindingTicket = bindingTicket {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
  }

  final String phone;
  final String? deviceId;
  final String? platform;
  final String? appVersion;
  final String? sourceOperation;
  final String? bindingTicket;

  Map<String, Object?> toJson() => <String, Object?>{
    "phone": this.phone,
    if (this.deviceId != null) "deviceId": this.deviceId!,
    if (this.platform != null) "platform": this.platform!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.sourceOperation != null) "sourceOperation": this.sourceOperation!,
    if (this.bindingTicket != null) "bindingTicket": this.bindingTicket!,
  };
}

CloudOperationRequestPayload encodeUserAuthenticationChallengeCreateAlipayAuthorizationRequestGeneratedRequest(CreateAlipayAuthorizationRequestCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.platform != null) "platform": request.platform!,
      if (request.appVersion != null) "appVersion": request.appVersion!,
    },
  );
}

CloudOperationRequestPayload encodeUserAuthenticationChallengeResolveOneTapLoginHintGeneratedRequest(ResolveOneTapLoginHintCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
    },
  );
}

CloudOperationRequestPayload encodeUserAuthenticationChallengeSendOtpGeneratedRequest(SendOtpCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      if (request.deviceId != null) "deviceId": request.deviceId!,
      if (request.platform != null) "platform": request.platform!,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      if (request.sourceOperation != null) "sourceOperation": request.sourceOperation!,
      if (request.bindingTicket != null) "bindingTicket": request.bindingTicket!,
    },
  );
}


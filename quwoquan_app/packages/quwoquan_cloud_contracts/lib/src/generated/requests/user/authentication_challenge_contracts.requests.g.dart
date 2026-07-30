// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/authentication_challenge_contracts.dart';

final class CreateAlipayAuthorizationRequestCommand {
  const CreateAlipayAuthorizationRequestCommand({
    String? platform,
    String? appVersion,
  }) : platform = platform,
       appVersion = appVersion;

  final String? platform;
  final String? appVersion;
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


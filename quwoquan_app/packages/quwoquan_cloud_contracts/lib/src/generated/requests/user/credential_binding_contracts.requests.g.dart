// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../user/credential_binding_contracts.dart';

final class BindCarrierPhoneCredentialCommand {
  BindCarrierPhoneCredentialCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       displayLabel = displayLabel {
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
  final String? displayLabel;
}

final class BindPhoneCredentialCommand {
  BindPhoneCredentialCommand({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) : phone = phone.trim(),
       otpCode = otpCode.trim(),
       displayLabel = displayLabel {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
    }
  }

  final String phone;
  final String otpCode;
  final String? displayLabel;
}

final class CompleteFederatedPhoneBindingCommand {
  CompleteFederatedPhoneBindingCommand({
    required String bindingTicket,
    required String phone,
    required String otpCode,
    required String challengeId,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : bindingTicket = bindingTicket.trim(),
       phone = phone.trim(),
       otpCode = otpCode.trim(),
       challengeId = challengeId.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim(),
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.bindingTicket.isEmpty) {
      throw ArgumentError.value(this.bindingTicket, "bindingTicket", 'must not be blank');
    }
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
    }
    if (this.challengeId.isEmpty) {
      throw ArgumentError.value(this.challengeId, "challengeId", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(this.appVersion, "appVersion", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(this.agreementVersion, "agreementVersion", 'must not be blank');
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(this.privacyVersion, "privacyVersion", 'must not be blank');
    }
  }

  final String bindingTicket;
  final String phone;
  final String otpCode;
  final String challengeId;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;
}

final class ListCredentialsQuery {
  const ListCredentialsQuery();
}

final class UnbindCredentialCommand {
  UnbindCredentialCommand({
    required String credentialType,
  }) : credentialType = credentialType.trim() {
    if (this.credentialType.isEmpty) {
      throw ArgumentError.value(this.credentialType, "credentialType", 'must not be blank');
    }
  }

  final String credentialType;
}

CloudOperationRequestPayload encodeUserCredentialBindingBindCarrierPhoneCredentialGeneratedRequest(BindCarrierPhoneCredentialCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.displayLabel != null) "displayLabel": request.displayLabel!,
    },
  );
}

CloudOperationRequestPayload encodeUserCredentialBindingBindPhoneCredentialGeneratedRequest(BindPhoneCredentialCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      "otpCode": request.otpCode,
      if (request.displayLabel != null) "displayLabel": request.displayLabel!,
    },
  );
}

CloudOperationRequestPayload encodeUserCredentialBindingCompleteFederatedPhoneBindingGeneratedRequest(CompleteFederatedPhoneBindingCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "bindingTicket": request.bindingTicket,
      "phone": request.phone,
      "otpCode": request.otpCode,
      "challengeId": request.challengeId,
      "deviceId": request.deviceId,
      "platform": request.platform,
      "appVersion": request.appVersion,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserCredentialBindingListCredentialsGeneratedRequest(ListCredentialsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeUserCredentialBindingUnbindCredentialGeneratedRequest(UnbindCredentialCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "credentialType": request.credentialType,
    },
  );
}


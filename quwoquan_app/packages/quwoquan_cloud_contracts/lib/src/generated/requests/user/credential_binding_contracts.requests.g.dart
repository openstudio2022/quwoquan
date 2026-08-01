// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.displayLabel != null) "displayLabel": this.displayLabel!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "phone": this.phone,
    "otpCode": this.otpCode,
    if (this.displayLabel != null) "displayLabel": this.displayLabel!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "bindingTicket": this.bindingTicket,
    "phone": this.phone,
    "otpCode": this.otpCode,
    "challengeId": this.challengeId,
    "deviceId": this.deviceId,
    "platform": this.platform,
    "appVersion": this.appVersion,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "credentialType": this.credentialType,
  };
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


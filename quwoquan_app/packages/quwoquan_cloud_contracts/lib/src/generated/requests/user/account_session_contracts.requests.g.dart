// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/account_session_contracts.dart';

final class LoginAnonymousCommand {
  LoginAnonymousCommand({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) : installId = installId.trim(),
       deviceFingerprintHash = deviceFingerprintHash.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim() {
    if (this.installId.isEmpty) {
      throw ArgumentError.value(this.installId, "installId", 'must not be blank');
    }
    if (this.deviceFingerprintHash.isEmpty) {
      throw ArgumentError.value(this.deviceFingerprintHash, "deviceFingerprintHash", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(this.appVersion, "appVersion", 'must not be blank');
    }
  }

  final String installId;
  final String deviceFingerprintHash;
  final String platform;
  final String appVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "installId": this.installId,
    "deviceFingerprintHash": this.deviceFingerprintHash,
    "platform": this.platform,
    "appVersion": this.appVersion,
  };
}

final class LoginOneTapCommand {
  LoginOneTapCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
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
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(this.agreementVersion, "agreementVersion", 'must not be blank');
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(this.privacyVersion, "privacyVersion", 'must not be blank');
    }
  }

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithAlipayCommand {
  LoginWithAlipayCommand({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : alipayAuthCode = alipayAuthCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.alipayAuthCode.isEmpty) {
      throw ArgumentError.value(this.alipayAuthCode, "alipayAuthCode", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(this.agreementVersion, "agreementVersion", 'must not be blank');
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(this.privacyVersion, "privacyVersion", 'must not be blank');
    }
  }

  final String alipayAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "alipayAuthCode": this.alipayAuthCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithPhoneCommand {
  LoginWithPhoneCommand({
    required String phone,
    required String otpCode,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : phone = phone.trim(),
       otpCode = otpCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim(),
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
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

  final String phone;
  final String otpCode;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "phone": this.phone,
    "otpCode": this.otpCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    "appVersion": this.appVersion,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithQqCommand {
  LoginWithQqCommand({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : qqAuthCode = qqAuthCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.qqAuthCode.isEmpty) {
      throw ArgumentError.value(this.qqAuthCode, "qqAuthCode", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(this.agreementVersion, "agreementVersion", 'must not be blank');
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(this.privacyVersion, "privacyVersion", 'must not be blank');
    }
  }

  final String qqAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "qqAuthCode": this.qqAuthCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithWechatCommand {
  LoginWithWechatCommand({
    required String wechatCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : wechatCode = wechatCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.wechatCode.isEmpty) {
      throw ArgumentError.value(this.wechatCode, "wechatCode", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(this.agreementVersion, "agreementVersion", 'must not be blank');
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(this.privacyVersion, "privacyVersion", 'must not be blank');
    }
  }

  final String wechatCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "wechatCode": this.wechatCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LogoutCommand {
  const LogoutCommand({
    String? refreshToken,
    String? deviceId,
  }) : refreshToken = refreshToken,
       deviceId = deviceId;

  final String? refreshToken;
  final String? deviceId;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.refreshToken != null) "refreshToken": this.refreshToken!,
    if (this.deviceId != null) "deviceId": this.deviceId!,
  };
}

final class RefreshTokenCommand {
  RefreshTokenCommand({
    required String refreshToken,
  }) : refreshToken = refreshToken.trim() {
    if (this.refreshToken.isEmpty) {
      throw ArgumentError.value(this.refreshToken, "refreshToken", 'must not be blank');
    }
  }

  final String refreshToken;

  Map<String, Object?> toJson() => <String, Object?>{
    "refreshToken": this.refreshToken,
  };
}

CloudOperationRequestPayload encodeUserAccountSessionLoginAnonymousGeneratedRequest(LoginAnonymousCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "installId": request.installId,
      "deviceFingerprintHash": request.deviceFingerprintHash,
      "platform": request.platform,
      "appVersion": request.appVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLoginOneTapGeneratedRequest(LoginOneTapCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLoginWithAlipayGeneratedRequest(LoginWithAlipayCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "alipayAuthCode": request.alipayAuthCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLoginWithPhoneGeneratedRequest(LoginWithPhoneCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      "otpCode": request.otpCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      "appVersion": request.appVersion,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLoginWithQqGeneratedRequest(LoginWithQqCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "qqAuthCode": request.qqAuthCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLoginWithWechatGeneratedRequest(LoginWithWechatCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "wechatCode": request.wechatCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLogoutGeneratedRequest(LogoutCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.refreshToken != null) "refreshToken": request.refreshToken!,
      if (request.deviceId != null) "deviceId": request.deviceId!,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionRefreshTokenGeneratedRequest(RefreshTokenCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "refreshToken": request.refreshToken,
    },
  );
}


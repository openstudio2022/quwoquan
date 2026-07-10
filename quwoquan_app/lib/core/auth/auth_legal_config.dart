import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

class AuthLegalConfig {
  const AuthLegalConfig._();

  static const String agreementVersion = String.fromEnvironment(
    'APP_USER_AGREEMENT_VERSION',
    defaultValue: '2026-07',
  );

  static const String privacyVersion = String.fromEnvironment(
    'APP_PRIVACY_POLICY_VERSION',
    defaultValue: '2026-07',
  );

  static const String _legalBaseUrlOverride = String.fromEnvironment(
    'APP_LEGAL_BASE_URL',
    defaultValue: '',
  );

  static const String _userAgreementUrlOverride = String.fromEnvironment(
    'APP_USER_AGREEMENT_URL',
    defaultValue: '',
  );

  static const String _privacyPolicyUrlOverride = String.fromEnvironment(
    'APP_PRIVACY_POLICY_URL',
    defaultValue: '',
  );

  static String get legalBaseUrl {
    final override = _legalBaseUrlOverride.trim();
    if (override.isNotEmpty) {
      return _stripTrailingSlash(override);
    }
    return '${CloudRuntimeConfig.gatewayBaseUrl}/legal';
  }

  static String get userAgreementUrl {
    final override = _userAgreementUrlOverride.trim();
    if (override.isNotEmpty) {
      return override;
    }
    return '$legalBaseUrl/user-agreement';
  }

  static String get privacyPolicyUrl {
    final override = _privacyPolicyUrlOverride.trim();
    if (override.isNotEmpty) {
      return override;
    }
    return '$legalBaseUrl/privacy-policy';
  }

  static String get permissionsUrl => '$legalBaseUrl/permissions';

  static String get thirdPartySdkListUrl =>
      '$legalBaseUrl/third-party-sdk-list';

  static String _stripTrailingSlash(String value) {
    var next = value;
    while (next.endsWith('/')) {
      next = next.substring(0, next.length - 1);
    }
    return next;
  }
}

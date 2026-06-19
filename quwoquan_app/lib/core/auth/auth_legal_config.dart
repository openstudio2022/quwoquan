import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

class AuthLegalConfig {
  const AuthLegalConfig._();

  static const String agreementVersion = String.fromEnvironment(
    'APP_USER_AGREEMENT_VERSION',
    defaultValue: '2026-05',
  );

  static const String privacyVersion = String.fromEnvironment(
    'APP_PRIVACY_POLICY_VERSION',
    defaultValue: '2026-05',
  );

  static const String _userAgreementUrlOverride = String.fromEnvironment(
    'APP_USER_AGREEMENT_URL',
    defaultValue: '',
  );

  static const String _privacyPolicyUrlOverride = String.fromEnvironment(
    'APP_PRIVACY_POLICY_URL',
    defaultValue: '',
  );

  static String get userAgreementUrl {
    final override = _userAgreementUrlOverride.trim();
    if (override.isNotEmpty) {
      return override;
    }
    return '${CloudRuntimeConfig.gatewayBaseUrl}/legal/user-agreement';
  }

  static String get privacyPolicyUrl {
    final override = _privacyPolicyUrlOverride.trim();
    if (override.isNotEmpty) {
      return override;
    }
    return '${CloudRuntimeConfig.gatewayBaseUrl}/legal/privacy-policy';
  }
}

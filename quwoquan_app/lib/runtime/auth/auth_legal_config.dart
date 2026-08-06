import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

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

  static String get legalBaseUrl =>
      _stripTrailingSlash(CloudRuntimeConfig.legalBaseUrl);

  static String get userAgreementUrl => '$legalBaseUrl/user-agreement';

  static String get privacyPolicyUrl => '$legalBaseUrl/privacy-policy';

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

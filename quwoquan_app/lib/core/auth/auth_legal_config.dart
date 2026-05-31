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

  static const String userAgreementUrl = String.fromEnvironment(
    'APP_USER_AGREEMENT_URL',
    defaultValue: 'https://www.quwoquan.com/legal/user-agreement',
  );

  static const String privacyPolicyUrl = String.fromEnvironment(
    'APP_PRIVACY_POLICY_URL',
    defaultValue: 'https://www.quwoquan.com/legal/privacy-policy',
  );
}

part of 'app_router.dart';

List<GoRoute> _legalDocumentRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.legalUserAgreement,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPage(
        title: FoundationText.userAgreement,
        url: AuthLegalConfig.userAgreementUrl,
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPrivacyPolicy,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPage(
        title: FoundationText.privacyPolicy,
        url: AuthLegalConfig.privacyPolicyUrl,
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPermissions,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPage(
        title: FoundationText.permissionsStatement,
        url: AuthLegalConfig.permissionsUrl,
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalThirdPartySdkList,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPage(
        title: FoundationText.thirdPartySdkList,
        url: AuthLegalConfig.thirdPartySdkListUrl,
      ),
    ),
  ),
];

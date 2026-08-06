part of 'app_router.dart';

List<GoRoute> _legalDocumentRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.legalUserAgreement,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: Consumer(
        builder: (context, ref, _) => LegalDocumentPage(
          title: FoundationText.userAgreement,
          url: AuthLegalConfig.userAgreementUrl,
          journeyEventTracker: ref.read(journeyEventTrackerProvider),
        ),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPrivacyPolicy,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: Consumer(
        builder: (context, ref, _) => LegalDocumentPage(
          title: FoundationText.privacyPolicy,
          url: AuthLegalConfig.privacyPolicyUrl,
          journeyEventTracker: ref.read(journeyEventTrackerProvider),
        ),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPermissions,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: Consumer(
        builder: (context, ref, _) => LegalDocumentPage(
          title: FoundationText.permissionsStatement,
          url: AuthLegalConfig.permissionsUrl,
          journeyEventTracker: ref.read(journeyEventTrackerProvider),
        ),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalThirdPartySdkList,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: Consumer(
        builder: (context, ref, _) => LegalDocumentPage(
          title: FoundationText.thirdPartySdkList,
          url: AuthLegalConfig.thirdPartySdkListUrl,
          journeyEventTracker: ref.read(journeyEventTrackerProvider),
        ),
      ),
    ),
  ),
];

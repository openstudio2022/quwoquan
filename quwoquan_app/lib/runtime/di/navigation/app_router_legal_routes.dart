part of 'app_router.dart';

List<GoRoute> _legalDocumentRoutes(Ref ref) => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.legalUserAgreement,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPageRouteHost(
        kind: LegalDocumentRouteKind.userAgreement,
        journeyEventTracker: ref.read(journeyEventTrackerProvider),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPrivacyPolicy,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPageRouteHost(
        kind: LegalDocumentRouteKind.privacyPolicy,
        journeyEventTracker: ref.read(journeyEventTrackerProvider),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalPermissions,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPageRouteHost(
        kind: LegalDocumentRouteKind.permissions,
        journeyEventTracker: ref.read(journeyEventTrackerProvider),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.legalThirdPartySdkList,
    pageBuilder: (context, state) => CupertinoPage<void>(
      key: state.pageKey,
      child: LegalDocumentPageRouteHost(
        kind: LegalDocumentRouteKind.thirdPartySdkList,
        journeyEventTracker: ref.read(journeyEventTrackerProvider),
      ),
    ),
  ),
];

part of 'app_router.dart';

List<GoRoute> _contactRoutes() => [
  GoRoute(
    path: AppRoutePaths.addContact,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      kind: AppRoutePageKind.fullscreenDialog,
      fullscreenDialog: true,
      child: const AddContactPage(),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.addContactScan,
    pageBuilder: (context, state) =>
        appRoutePage<void>(state: state, child: const ScanContactQrPage()),
  ),
  GoRoute(
    path: AppRoutePaths.addContactPhone,
    pageBuilder: (context, state) =>
        appRoutePage<void>(state: state, child: const PhoneContactsPage()),
  ),
  GoRoute(
    path: AppRoutePaths.addContactSearchPathTemplate,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: ContactSearchResultPage(
        initialQuery: state.uri.queryParameters['query'] ?? '',
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.addContactConfirmPathTemplate,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: ContactConfirmPage(
        targetUserId: state.uri.queryParameters['userId'] ?? '',
        handle: state.uri.queryParameters['handle'] ?? '',
        source: state.uri.queryParameters['source'] ?? '',
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.myQrCode,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: const MyQrCodePage(sharePresenter: profileQrSharePresenter),
    ),
  ),
];

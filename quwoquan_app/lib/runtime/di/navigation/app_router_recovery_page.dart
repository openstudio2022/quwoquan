part of 'app_router.dart';

/// Router error-page wiring. The recovery presentation is owned by
/// runtime/shell/recovery; navigation only selects its canonical mount.
Widget _buildRouterRecoveryPage() => const StartupRecoveryPage.routerError();

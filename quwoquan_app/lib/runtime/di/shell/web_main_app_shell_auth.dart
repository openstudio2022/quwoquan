part of 'web_main_app_shell.dart';

bool _ensureWebShellLoggedInFor(
  BuildContext context,
  WidgetRef ref,
  AuthGateReason reason,
  String redirect,
) {
  final auth = ref.read(authSessionControllerProvider);
  if (auth.isAuthenticated) {
    return true;
  }
  openLoginPage(
    context,
    reasonName: reason.name,
    redirect: redirect,
    dismissFallback: AppRoutePaths.home,
    dismissPolicy: LoginDismissPolicy.safeFallback,
  );
  return false;
}

bool _selectWebShellPrimaryDestination({
  required BuildContext context,
  required WidgetRef ref,
  required MainTabDestination destination,
}) {
  if (destination == MainTabDestination.chat) {
    return _ensureWebShellLoggedInFor(
      context,
      ref,
      AuthGateReason.openChat,
      AppRoutePaths.chat,
    );
  }
  if (destination == MainTabDestination.profile) {
    return _ensureWebShellLoggedInFor(
      context,
      ref,
      AuthGateReason.profileTab,
      AppRoutePaths.profile,
    );
  }
  return true;
}

class _WebContextTabSpec {
  const _WebContextTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

class _CreateCardSpec {
  const _CreateCardSpec({
    required this.id,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.action,
  });

  final String id;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback action;
}

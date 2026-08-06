part of 'login_page.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
  });

  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final LoginDismissPolicy dismissPolicy;

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class WebInlineLoginSurface extends StatelessWidget {
  const WebInlineLoginSurface({
    super.key,
    required this.onDismiss,
    required this.onLoggedIn,
    this.reason,
  });

  final VoidCallback onDismiss;
  final VoidCallback onLoggedIn;
  final String? reason;

  @override
  Widget build(BuildContext context) {
    return LoginFrameHost(
      reason: reason,
      dismissPolicy: LoginDismissPolicy.hostControlledClose,
      onDismiss: onDismiss,
      onLoggedIn: onLoggedIn,
      surfaceMode: LoginSurfaceMode.inline,
    );
  }
}

class _LoginPageState extends ConsumerState<LoginPage> {
  @override
  Widget build(BuildContext context) {
    return LoginFrameHost(
      reason: widget.reason,
      redirect: widget.redirect,
      dismissFallback: widget.dismissFallback,
      dismissPolicy: widget.dismissPolicy,
      surfaceMode: LoginSurfaceMode.page,
    );
  }
}

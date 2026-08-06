part of 'login_page.dart';

class _LoginTopBar extends StatelessWidget {
  const _LoginTopBar({
    required this.onNavigate,
    required this.showBack,
    this.enabled = true,
  });

  final VoidCallback onNavigate;
  final bool showBack;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: Row(
        children: <Widget>[
          Semantics(
            button: true,
            enabled: enabled,
            label: showBack
                ? FoundationText.loginBackSemanticLabel
                : FoundationText.loginDismissSemanticLabel,
            child: AppNavigationBarIconButton(
              icon: showBack ? CupertinoIcons.back : CupertinoIcons.xmark,
              onPressed: enabled ? onNavigate : null,
              color: AppColors.iosLabel(context),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }
}

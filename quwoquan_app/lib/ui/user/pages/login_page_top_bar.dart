part of 'login_page.dart';

class _LoginTopBar extends StatelessWidget {
  const _LoginTopBar({
    required this.onDismiss,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
  });

  final VoidCallback onDismiss;

  final LoginDismissPolicy dismissPolicy;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Semantics(
          button: true,
          label: dismissPolicy == LoginDismissPolicy.popPrevious
              ? FoundationText.loginBackSemanticLabel
              : FoundationText.loginDismissSemanticLabel,
          child: AppNavigationBarIconButton(
            icon: dismissPolicy == LoginDismissPolicy.popPrevious
                ? CupertinoIcons.back
                : CupertinoIcons.xmark,
            onPressed: onDismiss,
            color: AppColors.iosLabel(context),
          ),
        ),
        const Spacer(),
      ],
    );
  }
}

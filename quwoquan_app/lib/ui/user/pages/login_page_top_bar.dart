part of 'login_page.dart';

class _LoginTopBar extends StatelessWidget {
  const _LoginTopBar({
    required this.onDismiss,
    this.allowGuestDismissPop = true,
  });

  final VoidCallback onDismiss;

  /// 强登录入口（关闭走安全兜底、禁止 pop 回受限触发点）按 iOS Modal leading
  /// 语义用 `xmark`（关闭语义）；可 pop 回上一页的软入口仍用 `back`（返回语义）。
  final bool allowGuestDismissPop;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Semantics(
          button: true,
          label: UITextConstants.loginDismissSemanticLabel,
          child: AppNavigationBarIconButton(
            icon: allowGuestDismissPop
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

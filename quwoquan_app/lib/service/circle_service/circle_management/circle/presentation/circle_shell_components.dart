part of 'circle_shell.dart';

// Circle 私有视图组件随 source owner 存放，不进入 runtime/di。

enum _CircleMoreAction {
  edit,
  manage,
  approval,
  voiceCall,
  videoCall,
  submitPost,
  invite,
  share,
  copyLink,
  report,
}

class _CircleToolbarButton extends StatelessWidget {
  const _CircleToolbarButton({
    required this.icon,
    required this.onPressed,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.appChromeActionButtonSize,
        AppSpacing.appChromeActionButtonSize,
      ),
      onPressed: onPressed,
      child: Container(
        width: AppSpacing.appChromeActionButtonSize,
        height: AppSpacing.appChromeActionButtonSize,
        decoration: BoxDecoration(
          color: backgroundColor,
          shape: BoxShape.circle,
        ),
        child: Icon(
          icon,
          size: AppSpacing.appChromeActionIconSize,
          color: foregroundColor,
        ),
      ),
    );
  }
}

class _SectionSurface extends StatelessWidget {
  const _SectionSurface({required this.isDark, required this.child});

  final bool isDark;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final bg = AppColors.iosGroupedSurface(context);
    final border = AppColors.iosSeparator(context);
    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
        border: Border.all(color: border.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.14 : 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _TabSpec {
  const _TabSpec({required this.type, required this.label});

  final String type;
  final String label;
}

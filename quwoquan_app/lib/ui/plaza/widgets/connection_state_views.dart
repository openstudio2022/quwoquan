import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 同频/广场连接通道的共享原子组件：行动阶梯 CTA、标签 chip、四态视图。
///
/// 四态（加载骨架 / 空引导 / 错误重试 / 权限引导）统一在此实现，连接中心与
/// 三个独立页共用，避免每页复制四态。所有固定文案来自 [PlazaTextConstants]，
/// 颜色/间距/字号走设计 token（守 R27 / verify_dart_semantic）。

/// 行动阶梯 CTA 行：主按钮填充强调色，次按钮弱底色。
class ConnectionActionBar extends StatelessWidget {
  const ConnectionActionBar({
    super.key,
    required this.actions,
    required this.onAction,
  });

  final List<ConnectionActionHint> actions;
  final void Function(ConnectionActionHint action) onAction;

  @override
  Widget build(BuildContext context) {
    if (actions.isEmpty) {
      return const SizedBox.shrink();
    }
    final accent = AppColors.iosAccent(context);
    return Row(
      children: <Widget>[
        for (var i = 0; i < actions.length; i++) ...<Widget>[
          if (i > 0) SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              hint: actions[i],
              accent: accent,
              onTap: () => onAction(actions[i]),
            ),
          ),
        ],
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.hint,
    required this.accent,
    required this.onTap,
  });

  final ConnectionActionHint hint;
  final Color accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary = hint.isPrimary;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: AppSpacing.forty,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: primary ? accent : accent.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Text(
          hint.label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.semiBold,
            color: primary ? CupertinoColors.white : accent,
          ),
        ),
      ),
    );
  }
}

/// 弱底色标签 pill（共同兴趣 / 行程标签 / 局标签）。
class ConnectionChip extends StatelessWidget {
  const ConnectionChip({
    super.key,
    required this.label,
    this.icon,
    this.emphasize = false,
  });

  final String label;
  final IconData? icon;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bg = emphasize
        ? accent.withValues(alpha: 0.12)
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary);
    final fg = emphasize ? accent : AppColors.iosSecondaryLabel(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupMd,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...<Widget>[
            Icon(icon, size: AppSpacing.fourteen, color: fg),
            SizedBox(width: AppSpacing.intraGroupXs),
          ],
          Text(
            label,
            style: TextStyle(fontSize: AppTypography.iosCaption1, color: fg),
          ),
        ],
      ),
    );
  }
}

/// 加载骨架：复用「灰底圆角卡」节奏，给出 3 条占位。
class ConnectionLoadingView extends StatelessWidget {
  const ConnectionLoadingView({super.key, this.itemCount = 3});

  final int itemCount;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final base = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final shimmer = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );
    return ListView.separated(
      padding: EdgeInsets.all(AppSpacing.md),
      itemCount: itemCount,
      separatorBuilder: (_, _) => SizedBox(height: AppSpacing.md),
      itemBuilder: (_, _) => Container(
        height: AppSpacing.forty * 3,
        decoration: BoxDecoration(
          color: base,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
        ),
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _bar(shimmer, widthFactor: 0.5),
            SizedBox(height: AppSpacing.sm),
            _bar(shimmer, widthFactor: 0.8),
            const Spacer(),
            _bar(shimmer, widthFactor: 1, height: AppSpacing.twentyEight),
          ],
        ),
      ),
    );
  }

  Widget _bar(Color color, {required double widthFactor, double? height}) {
    return FractionallySizedBox(
      alignment: Alignment.centerLeft,
      widthFactor: widthFactor,
      child: Container(
        height: height ?? AppSpacing.fourteen,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
      ),
    );
  }
}

/// 空态：图标 + 标题 + 引导副文案。
class ConnectionEmptyView extends StatelessWidget {
  const ConnectionEmptyView({
    super.key,
    required this.title,
    required this.subtitle,
    this.icon = CupertinoIcons.sparkles,
  });

  final String title;
  final String subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return _CenteredState(
      icon: icon,
      title: title,
      subtitle: subtitle,
    );
  }
}

/// 错误态：标题 + 重试。
class ConnectionErrorView extends StatelessWidget {
  const ConnectionErrorView({super.key, required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _CenteredState(
      icon: CupertinoIcons.exclamationmark_circle,
      title: PlazaTextConstants.errorTitle,
      subtitle: '',
      action: _OutlineButton(
        label: PlazaTextConstants.errorRetry,
        onTap: onRetry,
      ),
    );
  }
}

/// 权限态：附近通道未授权定位时的引导。
class ConnectionPermissionView extends StatelessWidget {
  const ConnectionPermissionView({super.key, required this.onGrant});

  final VoidCallback onGrant;

  @override
  Widget build(BuildContext context) {
    return _CenteredState(
      icon: CupertinoIcons.location_circle,
      title: PlazaTextConstants.permissionTitle,
      subtitle: PlazaTextConstants.permissionSubtitle,
      action: _FilledButton(
        label: PlazaTextConstants.permissionGrant,
        onTap: onGrant,
      ),
    );
  }
}

class _CenteredState extends StatelessWidget {
  const _CenteredState({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.action,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              icon,
              size: AppSpacing.forty,
              color: AppColors.iosTertiaryLabel(context),
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            if (subtitle.trim().isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.sm),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
            if (action != null) ...<Widget>[
              SizedBox(height: AppSpacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

class _FilledButton extends StatelessWidget {
  const _FilledButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: AppSpacing.forty,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: accent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.semiBold,
            color: CupertinoColors.white,
          ),
        ),
      ),
    );
  }
}

class _OutlineButton extends StatelessWidget {
  const _OutlineButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: AppSpacing.forty,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.semiBold,
            color: accent,
          ),
        ),
      ),
    );
  }
}

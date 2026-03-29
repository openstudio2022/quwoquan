import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

enum ProfileIosActionStyle { filled, tinted, outlined, plain }

enum ProfileIosIconButtonStyle { filled, tinted, plain }

class ProfileIosSectionHeader extends StatelessWidget {
  const ProfileIosSectionHeader({
    super.key,
    required this.title,
    this.trailing,
    this.padding,
  });

  final String title;
  final Widget? trailing;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final resolvedPadding =
        padding ??
        EdgeInsets.fromLTRB(
          AppSpacing.containerXs,
          0,
          AppSpacing.containerXs,
          AppSpacing.intraGroupSm,
        );
    return Padding(
      padding: resolvedPadding,
      child: Row(
        children: <Widget>[
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.iosSectionHeader,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosSecondaryLabel(context),
              letterSpacing: -0.08,
            ),
          ),
          const Spacer(),
          trailing ?? const SizedBox.shrink(),
        ],
      ),
    );
  }
}

class ProfileIosSectionCard extends StatelessWidget {
  const ProfileIosSectionCard({
    super.key,
    required this.child,
    this.padding,
    this.radius = AppSpacing.radiusTwenty,
    this.backgroundColor,
    this.borderColor,
    this.addShadow = false,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double radius;
  final Color? backgroundColor;
  final Color? borderColor;
  final bool addShadow;

  @override
  Widget build(BuildContext context) {
    final fill = backgroundColor ?? AppColors.iosGroupedSurface(context);
    final separator =
        borderColor ?? AppColors.iosSeparator(context).withValues(alpha: 0.16);
    final shadow = CupertinoTheme.of(context).brightness == Brightness.dark
        ? AppColors.black.withValues(alpha: 0.22)
        : AppColors.black.withValues(alpha: 0.05);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: separator, width: AppSpacing.hairline),
        boxShadow: addShadow
            ? <BoxShadow>[
                BoxShadow(
                  color: shadow,
                  blurRadius: AppSpacing.twenty,
                  offset: const Offset(0, 10),
                ),
              ]
            : null,
      ),
      child: child,
    );
  }
}

class ProfileIosGroupedSection extends StatelessWidget {
  const ProfileIosGroupedSection({
    super.key,
    required this.children,
    this.header,
    this.footer,
    this.margin,
    this.showDividers = true,
  });

  final List<Widget> children;
  final String? header;
  final Widget? footer;
  final EdgeInsetsGeometry? margin;
  final bool showDividers;

  @override
  Widget build(BuildContext context) {
    final sectionChildren = <Widget>[];
    for (var i = 0; i < children.length; i += 1) {
      sectionChildren.add(children[i]);
      if (showDividers && i != children.length - 1) {
        sectionChildren.add(
          Padding(
            padding: EdgeInsets.only(left: AppSpacing.containerMd),
            child: Container(
              height: AppSpacing.hairline,
              color: AppColors.iosSeparator(context).withValues(alpha: 0.32),
            ),
          ),
        );
      }
    }

    return Padding(
      padding:
          margin ??
          EdgeInsets.only(
            left: AppSpacing.containerMd,
            right: AppSpacing.containerMd,
            bottom: AppSpacing.interGroupMd,
          ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (header != null && header!.trim().isNotEmpty)
            ProfileIosSectionHeader(title: header!),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
            child: Container(
              color: AppColors.iosGroupedSurface(context),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: sectionChildren,
              ),
            ),
          ),
          if (footer != null) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            footer!,
          ],
        ],
      ),
    );
  }
}

class ProfileIosGroupedCell extends StatelessWidget {
  const ProfileIosGroupedCell({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.trailing,
    this.trailingText,
    this.onTap,
    this.showChevron = true,
    this.isDestructive = false,
    this.verticalPadding,
    this.minHeight = 54,
  });

  final String title;
  final String? subtitle;
  final Widget? leading;
  final Widget? trailing;
  final String? trailingText;
  final VoidCallback? onTap;
  final bool showChevron;
  final bool isDestructive;
  final double? verticalPadding;
  final double minHeight;

  @override
  Widget build(BuildContext context) {
    final labelColor = isDestructive
        ? AppColors.iosDestructive(context)
        : AppColors.iosLabel(context);
    final cell = ConstrainedBox(
      constraints: BoxConstraints(minHeight: minHeight),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: verticalPadding ?? AppSpacing.containerSm,
        ),
        child: Row(
          children: <Widget>[
            if (leading != null) ...<Widget>[
              leading!,
              SizedBox(width: AppSpacing.containerSm),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.regular,
                      color: labelColor,
                    ),
                  ),
                  if (subtitle != null && subtitle!.trim().isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      subtitle!,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                        height: AppTypography.lineHeightCompact,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (trailingText != null && trailingText!.trim().isNotEmpty) ...<Widget>[
              Flexible(
                child: Text(
                  trailingText!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
            ],
            trailing ?? const SizedBox.shrink(),
            if (showChevron) ...<Widget>[
              if (trailing != null) SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: AppColors.iosTertiaryLabel(context),
              ),
            ],
          ],
        ),
      ),
    );
    if (onTap == null) {
      return cell;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: cell,
    );
  }
}

class ProfileIosIconButton extends StatelessWidget {
  const ProfileIosIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.style = ProfileIosIconButtonStyle.tinted,
    this.size = 36,
    this.iconSize = 18,
    this.backgroundColor,
    this.foregroundColor,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final ProfileIosIconButtonStyle style;
  final double size;
  final double iconSize;
  final Color? backgroundColor;
  final Color? foregroundColor;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final label = AppColors.iosLabel(context);
    final background = backgroundColor ??
        switch (style) {
      ProfileIosIconButtonStyle.filled => accent,
      ProfileIosIconButtonStyle.tinted => AppColors.iosFill(context),
      ProfileIosIconButtonStyle.plain => AppColors.transparent,
    };
    final iconColor = foregroundColor ??
        switch (style) {
      ProfileIosIconButtonStyle.filled => CupertinoColors.white,
      ProfileIosIconButtonStyle.tinted => label,
      ProfileIosIconButtonStyle.plain => label,
    };
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onPressed,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: background,
          shape: BoxShape.circle,
          border: style == ProfileIosIconButtonStyle.plain
              ? Border.all(
                  color: AppColors.iosSeparator(context).withValues(alpha: 0.2),
                  width: AppSpacing.hairline,
                )
              : null,
        ),
        child: Icon(icon, size: iconSize, color: iconColor),
      ),
    );
  }
}

class ProfileIosActionButton extends StatelessWidget {
  const ProfileIosActionButton({
    super.key,
    required this.label,
    this.icon,
    this.onPressed,
    this.style = ProfileIosActionStyle.tinted,
    this.height = 36,
    this.expand = true,
    this.backgroundColor,
    this.foregroundColor,
    this.borderColor,
    this.labelFontWeight,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final ProfileIosActionStyle style;
  final double height;
  final bool expand;
  final Color? backgroundColor;
  final Color? foregroundColor;
  final Color? borderColor;
  final FontWeight? labelFontWeight;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground =
        foregroundColor ??
        switch (style) {
      ProfileIosActionStyle.filled => CupertinoColors.white,
      ProfileIosActionStyle.tinted => accent,
      ProfileIosActionStyle.outlined => AppColors.iosLabel(context),
      ProfileIosActionStyle.plain => accent,
    };
    final background =
        backgroundColor ??
        switch (style) {
      ProfileIosActionStyle.filled => accent,
      ProfileIosActionStyle.tinted => accent.withValues(
          alpha: isDark ? 0.24 : 0.12,
        ),
      ProfileIosActionStyle.outlined => AppColors.iosSystemBackground(context),
      ProfileIosActionStyle.plain => AppColors.transparent,
    };
    final resolvedBorderColor =
        borderColor ??
        switch (style) {
      ProfileIosActionStyle.outlined => AppColors.iosSeparator(
          context,
        ).withValues(alpha: 0.24),
      _ => AppColors.transparent,
    };

    Widget child = Container(
      height: height,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: resolvedBorderColor,
          width: AppSpacing.hairline,
        ),
      ),
      child: Center(
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (icon != null) ...<Widget>[
                Icon(icon, size: AppSpacing.iconSmall, color: foreground),
                SizedBox(width: AppSpacing.intraGroupXs),
              ],
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosButton,
                  fontWeight: labelFontWeight ?? AppTypography.semiBold,
                  color: foreground,
                  letterSpacing: -0.18,
                ),
              ),
            ],
          ),
        ),
      ),
    );

    if (!expand) {
      child = IntrinsicWidth(child: child);
    }

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(AppSpacing.minInteractiveSize, AppSpacing.minInteractiveSize),
      onPressed: onPressed,
      child: child,
    );
  }
}

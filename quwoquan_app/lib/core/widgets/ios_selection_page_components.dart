import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

enum IosSelectionHeaderLeadingStyle { back, close }

class IosSelectionPageScaffold extends StatelessWidget {
  const IosSelectionPageScaffold({
    super.key,
    required this.title,
    required this.onBack,
    required this.body,
    this.bottomBar,
    this.trailing,
    this.backgroundColor,
    this.pageKey,
    this.leadingStyle = IosSelectionHeaderLeadingStyle.back,
  });

  final String title;
  final VoidCallback onBack;
  final Widget body;
  final Widget? bottomBar;
  final Widget? trailing;
  final Color? backgroundColor;
  final Key? pageKey;
  final IosSelectionHeaderLeadingStyle leadingStyle;

  @override
  Widget build(BuildContext context) {
    final brightness =
        CupertinoTheme.of(context).brightness ??
        MediaQuery.platformBrightnessOf(context);
    final children = <Widget>[Expanded(child: body)];
    if (bottomBar != null) {
      children.add(bottomBar!);
    }
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppTheme.systemUiOverlayStyleFor(brightness),
      child: CupertinoPageScaffold(
        key: pageKey,
        backgroundColor:
            backgroundColor ?? AppColors.iosPageBackground(context),
        navigationBar: IosSelectionPageHeader(
          title: title,
          onBack: onBack,
          trailing: trailing,
          leadingStyle: leadingStyle,
        ),
        // Keep a transparent Material host, matching `AppScaffold`, to avoid
        // Cupertino pages rendering emphasized/underlined text artifacts on
        // some real-device accessibility/display combinations.
        child: Material(
          type: MaterialType.transparency,
          child: Column(children: children),
        ),
      ),
    );
  }
}

class IosSelectionPageHeader extends StatelessWidget
    implements ObstructingPreferredSizeWidget {
  const IosSelectionPageHeader({
    super.key,
    required this.title,
    required this.onBack,
    this.backLabel,
    this.trailing,
    this.leadingStyle = IosSelectionHeaderLeadingStyle.back,
  });

  final String title;
  final String? backLabel;
  final VoidCallback onBack;
  final Widget? trailing;
  final IosSelectionHeaderLeadingStyle leadingStyle;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final background = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: 0.94);
    final borderColor = AppColors.iosSeparator(context).withValues(alpha: 0.12);
    return CupertinoNavigationBar(
      backgroundColor: background,
      border: Border(
        bottom: BorderSide(color: borderColor, width: AppSpacing.hairline),
      ),
      automaticallyImplyLeading: false,
      leading: AppNavigationBarIconButton(
        icon: leadingStyle == IosSelectionHeaderLeadingStyle.back
            ? CupertinoIcons.back
            : CupertinoIcons.xmark,
        onPressed: onBack,
      ),
      middle: Text(
        title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
      ),
      trailing: trailing,
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(AppSpacing.toolbarHeight);

  @override
  bool shouldFullyObstruct(BuildContext context) => true;
}

class IosSelectionSectionHeader extends StatelessWidget {
  const IosSelectionSectionHeader({
    super.key,
    required this.title,
    this.padding,
  });

  final String title;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding:
          padding ??
          EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.interGroupSm,
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
          ),
      child: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.iosSectionHeader,
          fontWeight: AppTypography.semiBold,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class IosSelectionSection extends StatelessWidget {
  const IosSelectionSection({
    super.key,
    required this.child,
    this.addShadow = false,
  });

  final Widget child;
  final bool addShadow;

  @override
  Widget build(BuildContext context) {
    final borderColor = AppColors.iosSeparator(context).withValues(alpha: 0.06);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(
          AppSpacing.largeBorderRadius + AppSpacing.two,
        ),
        border: Border.all(color: borderColor, width: AppSpacing.hairline),
        boxShadow: addShadow
            ? <BoxShadow>[
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.025),
                  blurRadius: AppSpacing.avatarUserXs,
                  offset: const Offset(0, 6),
                ),
              ]
            : const <BoxShadow>[],
      ),
      child: child,
    );
  }
}

class IosSelectionOptionTile extends StatefulWidget {
  const IosSelectionOptionTile({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.trailing,
    this.additionalInfo,
    this.additionalInfoTextStyle,
    this.showChevron = false,
    this.onTap,
    this.backgroundColor,
    this.pressedColor,
    this.padding = const EdgeInsets.symmetric(
      horizontal: AppSpacing.containerMd,
      vertical: AppSpacing.containerSm,
    ),
    this.borderRadius = BorderRadius.zero,
    this.minimumHeight = AppSpacing.avatarUserLg + AppSpacing.containerSm,
  });

  final Widget title;
  final Widget? subtitle;
  final Widget? leading;
  final Widget? trailing;
  final String? additionalInfo;
  final TextStyle? additionalInfoTextStyle;
  final bool showChevron;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final Color? pressedColor;
  final EdgeInsetsGeometry padding;
  final BorderRadius borderRadius;
  final double minimumHeight;

  @override
  State<IosSelectionOptionTile> createState() => _IosSelectionOptionTileState();
}

class _IosSelectionOptionTileState extends State<IosSelectionOptionTile> {
  bool _pressed = false;

  bool get _isEnabled => widget.onTap != null;

  void _setPressed(bool value) {
    if (!_isEnabled || _pressed == value || !mounted) {
      return;
    }
    setState(() {
      _pressed = value;
    });
  }

  void _handleTap() {
    if (!_isEnabled) {
      return;
    }
    HapticFeedback.selectionClick();
    widget.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    final background =
        widget.backgroundColor ?? AppColors.iosSystemBackground(context);
    final pressedColor = widget.pressedColor ?? AppColors.iosFill(context);
    final chevronColor = AppColors.iosTertiaryLabel(context);
    final hasSubtitle = widget.subtitle != null;
    final additionalInfoText = (widget.additionalInfo ?? '').trim();
    final maxAdditionalInfoWidth = MediaQuery.sizeOf(context).width * 0.42;

    return AnimatedOpacity(
      duration: const Duration(milliseconds: 180),
      opacity: _isEnabled ? 1 : 0.52,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: _isEnabled ? (_) => _setPressed(true) : null,
        onTapCancel: _isEnabled ? () => _setPressed(false) : null,
        onTapUp: _isEnabled
            ? (_) {
                _setPressed(false);
                _handleTap();
              }
            : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          constraints: BoxConstraints(minHeight: widget.minimumHeight),
          padding: widget.padding,
          decoration: BoxDecoration(
            color: _pressed ? pressedColor : background,
            borderRadius: widget.borderRadius,
          ),
          child: Row(
            crossAxisAlignment: hasSubtitle
                ? CrossAxisAlignment.start
                : CrossAxisAlignment.center,
            children: <Widget>[
              if (widget.leading != null) ...<Widget>[
                widget.leading!,
                SizedBox(width: AppSpacing.containerSm),
              ],
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    widget.title,
                    if (widget.subtitle != null) ...<Widget>[
                      SizedBox(height: AppSpacing.intraGroupXs),
                      widget.subtitle!,
                    ],
                  ],
                ),
              ),
              if (additionalInfoText.isNotEmpty) ...<Widget>[
                SizedBox(width: AppSpacing.containerSm),
                Flexible(
                  flex: 0,
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      minWidth:
                          AppSpacing.avatarUserLg + AppSpacing.intraGroupSm,
                      maxWidth: maxAdditionalInfoWidth,
                    ),
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Text(
                        additionalInfoText,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.right,
                        style:
                            widget.additionalInfoTextStyle ??
                            TextStyle(
                              fontSize: AppTypography.iosBody,
                              color: AppColors.iosAccent(context),
                              fontWeight: AppTypography.normal,
                            ),
                      ),
                    ),
                  ),
                ),
              ],
              if (widget.trailing != null) ...<Widget>[
                SizedBox(width: AppSpacing.containerSm),
                widget.trailing!,
              ],
              if (widget.showChevron) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupSm),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: chevronColor.withValues(alpha: _isEnabled ? 1 : 0.6),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class IosSelectionInlineDivider extends StatelessWidget {
  const IosSelectionInlineDivider({
    super.key,
    this.indent = 0,
    this.endIndent = 0,
  });

  final double indent;
  final double endIndent;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(left: indent, right: endIndent),
      child: Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
      ),
    );
  }
}

class IosSelectionBottomBar extends StatelessWidget {
  const IosSelectionBottomBar({
    super.key,
    required this.onConfirm,
    this.onCancel,
    this.cancelLabel = UITextConstants.cancel,
    this.confirmLabel = UITextConstants.confirm,
    this.confirmButtonKey,
    this.cancelButtonKey,
    this.confirmEnabled = true,
    this.confirmLoading = false,
    /// When false, omits bottom safe area inset from media query — use when the
    /// parent sheet already applies `MediaQuery.viewPadding` on the panel.
    this.includeViewPaddingBottom = true,
  });

  final VoidCallback onConfirm;
  final VoidCallback? onCancel;
  final String cancelLabel;
  final String confirmLabel;
  final Key? confirmButtonKey;
  final Key? cancelButtonKey;
  final bool confirmEnabled;
  final bool confirmLoading;
  final bool includeViewPaddingBottom;

  @override
  Widget build(BuildContext context) {
    final cancelAction = onCancel;
    final background = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: 0.94);
    final separator = AppColors.iosSeparator(context).withValues(alpha: 0.12);

    final bottomInset = includeViewPaddingBottom
        ? MediaQuery.viewPaddingOf(context).bottom
        : 0.0;
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        bottomInset + AppSpacing.containerMd,
      ),
      decoration: BoxDecoration(
        color: background,
        border: Border(
          top: BorderSide(color: separator, width: AppSpacing.hairline),
        ),
      ),
      child: Row(
        children: <Widget>[
          if (cancelAction != null) ...<Widget>[
            Expanded(
              child: _IosSelectionActionButton(
                key: cancelButtonKey,
                label: cancelLabel,
                filled: false,
                onPressed: cancelAction,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
          ],
          Expanded(
            child: _IosSelectionActionButton(
              key: confirmButtonKey,
              label: confirmLabel,
              filled: true,
              onPressed: onConfirm,
              enabled: confirmEnabled,
              loading: confirmLoading,
            ),
          ),
        ],
      ),
    );
  }
}

class _IosSelectionActionButton extends StatelessWidget {
  const _IosSelectionActionButton({
    super.key,
    required this.label,
    required this.filled,
    required this.onPressed,
    this.enabled = true,
    this.loading = false,
  });

  final String label;
  final bool filled;
  final VoidCallback onPressed;
  final bool enabled;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final accent = AppColors.iosAccent(context).withValues(alpha: 0.92);
    final neutralBackground = AppColors.iosSecondaryFill(context);
    final neutralForeground = AppColors.iosLabel(context);
    final disabledBackground =
        SettingsSemanticConstants.actionButtonDisabledBackground(isDark);
    final disabledForeground =
        SettingsSemanticConstants.actionButtonDisabledForeground(isDark);
    final radius = AppSpacing.largeBorderRadius + AppSpacing.two;
    final background = enabled
        ? (filled ? accent : neutralBackground)
        : disabledBackground;
    final foreground = enabled
        ? (filled ? CupertinoColors.white : neutralForeground)
        : disabledForeground;

    return SizedBox(
      height: AppSpacing.buttonHeight,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(radius),
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          borderRadius: BorderRadius.circular(radius),
          onPressed: enabled && !loading ? onPressed : null,
          child: loading
              ? CupertinoActivityIndicator(color: foreground)
              : Text(
                  label,
                  style: TextStyle(
                    color: foreground,
                    fontSize: AppTypography.iosButton,
                    fontWeight: AppTypography.medium,
                  ),
                ),
        ),
      ),
    );
  }
}

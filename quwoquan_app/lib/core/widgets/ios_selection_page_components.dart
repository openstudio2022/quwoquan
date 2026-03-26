import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
  });

  final String title;
  final VoidCallback onBack;
  final Widget body;
  final Widget? bottomBar;
  final Widget? trailing;
  final Color? backgroundColor;
  final Key? pageKey;

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
  });

  final String title;
  final String? backLabel;
  final VoidCallback onBack;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final background = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: 0.94);
    final borderColor = AppColors.iosSeparator(context).withValues(alpha: 0.12);
    return CupertinoNavigationBar(
      backgroundColor: background,
      border: Border(
        bottom: BorderSide(color: borderColor, width: AppSpacing.hairline),
      ),
      leading: CupertinoNavigationBarBackButton(
        previousPageTitle: '',
        onPressed: onBack,
      ),
      middle: Text(
        title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: AppColors.iosLabel(context),
          fontSize: AppTypography.iosNavTitle,
          fontWeight: AppTypography.semiBold,
        ),
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
    final borderColor = AppColors.iosSeparator(context).withValues(alpha: 0.08);
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
              if ((widget.additionalInfo ?? '').trim().isNotEmpty) ...<Widget>[
                SizedBox(width: AppSpacing.containerSm),
                Flexible(
                  child: Text(
                    widget.additionalInfo!.trim(),
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
  });

  final VoidCallback onConfirm;
  final VoidCallback? onCancel;
  final String cancelLabel;
  final String confirmLabel;
  final Key? confirmButtonKey;
  final Key? cancelButtonKey;

  @override
  Widget build(BuildContext context) {
    final cancelAction = onCancel;
    final background = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: 0.94);
    final separator = AppColors.iosSeparator(context).withValues(alpha: 0.12);

    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerMd,
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
  });

  final String label;
  final bool filled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final radius = AppSpacing.largeBorderRadius + AppSpacing.two;

    return SizedBox(
      height: AppSpacing.buttonHeight,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: filled ? accent : AppColors.iosSecondaryFill(context),
          borderRadius: BorderRadius.circular(radius),
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          borderRadius: BorderRadius.circular(radius),
          onPressed: onPressed,
          child: Text(
            label,
            style: TextStyle(
              color: filled ? CupertinoColors.white : accent,
              fontSize: AppTypography.iosButton,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ),
      ),
    );
  }
}

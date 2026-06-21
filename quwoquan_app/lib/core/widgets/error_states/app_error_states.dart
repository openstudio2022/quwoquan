import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

typedef UiErrorActionCallback = Future<void> Function(UiErrorAction action);

const double _softErrorIllustrationSize = 80.0;

class AppPageErrorState extends StatelessWidget {
  const AppPageErrorState({
    super.key,
    required this.semantic,
    this.onAction,
    this.padding,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final resolvedSemantic = _withSafePageExit(context, semantic);
    final fallbackStyle = TextStyle(
      color: AppColors.iosLabel(context),
      fontSize: AppTypography.iosBody,
      decoration: TextDecoration.none,
    );
    return DefaultTextStyle(
      style: fallbackStyle,
      child: Padding(
        padding: EdgeInsets.zero,
        child: Center(
          child: Padding(
            padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppSpacing.feedMaxContentWidth,
              ),
              child: _ErrorEmptyPageBody(
                semantic: resolvedSemantic,
                onAction: onAction,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppSectionErrorCard extends StatelessWidget {
  const AppSectionErrorCard({
    super.key,
    required this.semantic,
    this.onAction,
    this.margin,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: margin ?? EdgeInsets.all(AppSpacing.containerMd),
      child: _ErrorSoftCardBody(semantic: semantic, onAction: onAction),
    );
  }
}

class AppTransientErrorNotice extends StatelessWidget {
  const AppTransientErrorNotice({
    super.key,
    required this.semantic,
    this.margin,
  });

  final UiErrorSemantic semantic;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final accent = _toneAccentColor(context, semantic.tone);
    return Padding(
      padding:
          margin ??
          EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.intraGroupSm,
          ),
      child: Align(
        alignment: Alignment.topCenter,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: accent.withValues(alpha: isDark ? 0.18 : 0.08),
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerMd,
              vertical: AppSpacing.sm,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Container(
                  width: AppSpacing.xs,
                  height: AppSpacing.xs,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.75),
                    shape: BoxShape.circle,
                  ),
                ),
                SizedBox(width: AppSpacing.sm),
                Flexible(
                  child: Text(
                    semantic.message,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: foreground.withValues(alpha: 0.78),
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AppListAppendErrorFooter extends StatelessWidget {
  const AppListAppendErrorFooter({
    super.key,
    required this.semantic,
    this.onAction,
    this.padding,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final action = semantic.primaryAction;
    return Padding(
      padding:
          padding ??
          EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.interGroupMd,
          ),
      child: Center(
        child: CupertinoButton(
          minimumSize: const Size(
            AppSpacing.minInteractiveSize,
            AppSpacing.minInteractiveSize,
          ),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.sm,
          ),
          color: AppColors.iosSecondaryFill(context).withValues(alpha: 0.45),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
          onPressed: action == null || onAction == null
              ? null
              : () => unawaited(onAction!(action)),
          child: Text(
            action == null ? semantic.message : semantic.message,
            style: TextStyle(
              color: secondary,
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.medium,
            ),
          ),
        ),
      ),
    );
  }
}

class AppInlineGateState extends StatelessWidget {
  const AppInlineGateState({
    super.key,
    required this.semantic,
    this.onAction,
    this.margin,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: margin ?? EdgeInsets.all(AppSpacing.containerMd),
      child: _ErrorSoftCardBody(
        semantic: semantic,
        onAction: onAction,
        gate: true,
      ),
    );
  }
}

class AppActionErrorFeedback {
  const AppActionErrorFeedback._();

  static Future<void> show(
    BuildContext context, {
    required UiErrorSemantic semantic,
    UiErrorActionCallback? onAction,
  }) async {
    final primary = semantic.primaryAction;
    if (primary == null) {
      AppToast.show(context, semantic.message);
      return;
    }
    if (!context.mounted) {
      return;
    }
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(semantic.title),
        content: Text(semantic.message),
        actions: <Widget>[
          if (semantic.secondaryAction != null)
            CupertinoDialogAction(
              onPressed: () {
                Navigator.of(dialogContext).pop();
                if (onAction != null) {
                  unawaited(onAction(semantic.secondaryAction!));
                }
              },
              child: Text(semantic.secondaryAction!.label),
            ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              Navigator.of(dialogContext).pop();
              if (onAction != null) {
                unawaited(onAction(primary));
              }
            },
            child: Text(primary.label),
          ),
        ],
      ),
    );
  }
}

class _ErrorEmptyPageBody extends StatelessWidget {
  const _ErrorEmptyPageBody({required this.semantic, this.onAction});

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final titleColor = AppColors.iosLabel(context);
    final messageColor = AppColors.iosSecondaryLabel(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        const _SoftPlanetIllustration(),
        SizedBox(height: AppSpacing.interGroupMd),
        Text(
          semantic.title,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosTitle3,
            fontWeight: AppTypography.semiBold,
            color: titleColor,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Text(
          semantic.message,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: messageColor,
            height: AppSpacing.textLineHeightBody,
          ),
        ),
        if ((semantic.secondaryMessage ?? '').trim().isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            semantic.secondaryMessage!.trim(),
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosTertiaryLabel(context),
              height: AppSpacing.textLineHeightFootnote,
            ),
          ),
        ],
        if (semantic.primaryAction != null ||
            semantic.secondaryAction != null) ...<Widget>[
          SizedBox(height: AppSpacing.interGroupMd),
          _ErrorActionRow(semantic: semantic, onAction: onAction),
        ],
      ],
    );
  }
}

class _ErrorSoftCardBody extends StatelessWidget {
  const _ErrorSoftCardBody({
    required this.semantic,
    this.onAction,
    this.gate = false,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final bool gate;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = AppColors.iosSecondaryFill(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.35);
    final accent = _toneAccentColor(context, semantic.tone);
    final titleColor = AppColors.iosLabel(context);
    final messageColor = AppColors.iosSecondaryLabel(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Container(
              width: AppSpacing.sm,
              height: AppSpacing.sm,
              margin: EdgeInsets.only(top: AppSpacing.xs),
              decoration: BoxDecoration(
                color: accent.withValues(alpha: gate ? 0.8 : 0.55),
                shape: BoxShape.circle,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    semantic.title,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: titleColor,
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs),
                  Text(
                    semantic.message,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: messageColor,
                      height: AppSpacing.textLineHeightFootnote,
                    ),
                  ),
                  if ((semantic.secondaryMessage ?? '')
                      .trim()
                      .isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      semantic.secondaryMessage!.trim(),
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosTertiaryLabel(context),
                        height: AppSpacing.textLineHeightCaption,
                      ),
                    ),
                  ],
                  if (semantic.primaryAction != null ||
                      semantic.secondaryAction != null) ...<Widget>[
                    SizedBox(height: AppSpacing.containerSm),
                    _ErrorActionRow(
                      semantic: semantic,
                      onAction: onAction,
                      compact: true,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorActionRow extends StatelessWidget {
  const _ErrorActionRow({
    required this.semantic,
    this.onAction,
    this.compact = false,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      alignment: compact ? WrapAlignment.start : WrapAlignment.center,
      spacing: AppSpacing.containerSm,
      runSpacing: AppSpacing.containerSm,
      children: <Widget>[
        if (semantic.secondaryAction != null)
          CupertinoButton(
            minimumSize: compact
                ? const Size(
                    AppSpacing.minInteractiveSize,
                    AppSpacing.minInteractiveSize,
                  )
                : null,
            padding: EdgeInsets.symmetric(
              horizontal: compact ? AppSpacing.sm : AppSpacing.containerMd,
              vertical: compact ? AppSpacing.xs : AppSpacing.sm,
            ),
            onPressed: _canDispatch(semantic.secondaryAction!)
                ? () => unawaited(
                    _dispatchAction(context, semantic.secondaryAction!),
                  )
                : null,
            child: Text(semantic.secondaryAction!.label),
          ),
        if (semantic.primaryAction != null)
          CupertinoButton(
            minimumSize: compact
                ? const Size(
                    AppSpacing.minInteractiveSize,
                    AppSpacing.minInteractiveSize,
                  )
                : null,
            padding: EdgeInsets.symmetric(
              horizontal: compact
                  ? AppSpacing.containerSm
                  : AppSpacing.containerLg,
              vertical: compact ? AppSpacing.xs : AppSpacing.sm,
            ),
            color: AppColors.iosTintedFill(context),
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            onPressed: _canDispatch(semantic.primaryAction!)
                ? () => unawaited(
                    _dispatchAction(context, semantic.primaryAction!),
                  )
                : null,
            child: Text(
              semantic.primaryAction!.label,
              style: TextStyle(
                color: AppColors.iosAccent(context),
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
      ],
    );
  }

  Future<void> _dispatchAction(
    BuildContext context,
    UiErrorAction action,
  ) async {
    if (action.type == UiErrorActionType.back) {
      _popOrGoHome(context);
      return;
    }
    if (onAction == null) {
      return;
    }
    await onAction!(action);
  }

  bool _canDispatch(UiErrorAction action) {
    return action.type == UiErrorActionType.back || onAction != null;
  }
}

class _SoftPlanetIllustration extends StatelessWidget {
  const _SoftPlanetIllustration();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: const Size(_softErrorIllustrationSize, _softErrorIllustrationSize),
      painter: _SoftPlanetPainter(
        planetColor: AppColors.iosTintedFill(context),
        orbitColor: AppColors.iosAccent(context).withValues(alpha: 0.62),
        signalColor: AppColors.iosTertiaryLabel(
          context,
        ).withValues(alpha: 0.35),
      ),
    );
  }
}

class _SoftPlanetPainter extends CustomPainter {
  const _SoftPlanetPainter({
    required this.planetColor,
    required this.orbitColor,
    required this.signalColor,
  });

  final Color planetColor;
  final Color orbitColor;
  final Color signalColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final planetPaint = Paint()..color = planetColor;
    canvas.drawCircle(center, size.width * 0.22, planetPaint);

    final orbitPaint = Paint()
      ..color = orbitColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.hairline * 4
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(-math.pi / 7);
    canvas.drawArc(
      Rect.fromCenter(
        center: Offset.zero,
        width: size.width * 0.72,
        height: size.height * 0.32,
      ),
      math.pi * 0.08,
      math.pi * 1.55,
      false,
      orbitPaint,
    );
    canvas.restore();

    final signalPaint = Paint()
      ..color = signalColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.hairline * 3
      ..strokeCap = StrokeCap.round;
    final signalOrigin = Offset(size.width * 0.64, size.height * 0.24);
    for (var i = 0; i < 2; i++) {
      final radius = size.width * (0.11 + i * 0.09);
      canvas.drawArc(
        Rect.fromCircle(center: signalOrigin, radius: radius),
        -math.pi / 2.4,
        math.pi / 2.5,
        false,
        signalPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SoftPlanetPainter oldDelegate) {
    return oldDelegate.planetColor != planetColor ||
        oldDelegate.orbitColor != orbitColor ||
        oldDelegate.signalColor != signalColor;
  }
}

Color _toneAccentColor(BuildContext context, UiErrorTone tone) {
  return switch (tone) {
    UiErrorTone.info => AppColors.iosAccent(context),
    UiErrorTone.caution => CupertinoDynamicColor.resolve(
      CupertinoColors.systemOrange,
      context,
    ),
    UiErrorTone.critical => AppColors.iosDestructive(context),
    UiErrorTone.neutral => AppColors.iosSecondaryLabel(context),
  };
}

UiErrorSemantic _withSafePageExit(
  BuildContext context,
  UiErrorSemantic semantic,
) {
  if (semantic.scope != UiErrorScope.page) {
    return semantic;
  }
  final backAction = UiErrorAction(
    type: UiErrorActionType.back,
    label: UITextConstants.back,
  );
  final primary = semantic.primaryAction;
  final secondary = semantic.secondaryAction;
  if (primary == null && secondary == null) {
    return UiErrorSemantic(
      category: semantic.category,
      scope: semantic.scope,
      title: semantic.title,
      message: semantic.message,
      secondaryMessage: semantic.secondaryMessage,
      primaryAction: backAction,
      secondaryAction: null,
      dismissible: semantic.dismissible,
      sourceCode: semantic.sourceCode,
      failureKind: semantic.failureKind,
      copyKey: semantic.copyKey,
      recoveryAction: semantic.recoveryAction,
      presentation: semantic.presentation,
      tone: semantic.tone,
    );
  }
  final shouldAppendBack =
      secondary == null &&
      primary != null &&
      primary.type != UiErrorActionType.back &&
      primary.type != UiErrorActionType.login &&
      primary.type != UiErrorActionType.openSettings;
  if (!shouldAppendBack) {
    return semantic;
  }
  return UiErrorSemantic(
    category: semantic.category,
    scope: semantic.scope,
    title: semantic.title,
    message: semantic.message,
    secondaryMessage: semantic.secondaryMessage,
    primaryAction: primary,
    secondaryAction: backAction,
    dismissible: semantic.dismissible,
    sourceCode: semantic.sourceCode,
    failureKind: semantic.failureKind,
    copyKey: semantic.copyKey,
    recoveryAction: semantic.recoveryAction,
    presentation: semantic.presentation,
    tone: semantic.tone,
  );
}

void _popOrGoHome(BuildContext context) {
  final navigator = Navigator.maybeOf(context);
  if (navigator != null && navigator.canPop()) {
    navigator.pop();
    return;
  }
  final router = GoRouter.maybeOf(context);
  if (router != null) {
    router.go(AppRoutePaths.home);
  }
}

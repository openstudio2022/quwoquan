import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';

part 'app_error_state_visuals.dart';

typedef UiErrorActionCallback = Future<void> Function(UiErrorAction action);

const double _softErrorIllustrationSize = 80.0;

class AppPageErrorState extends StatefulWidget {
  const AppPageErrorState({
    super.key,
    required this.semantic,
    this.onAction,
    this.padding,
    this.experienceTracker,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry? padding;
  final AppPageExperienceTracker? experienceTracker;

  @override
  State<AppPageErrorState> createState() => _AppPageErrorStateState();
}

class _AppPageErrorStateState extends State<AppPageErrorState> {
  late DateTime _shownAt;
  Future<void> _telemetryTail = Future<void>.value();

  AppPageExperienceTracker get _experienceTracker =>
      widget.experienceTracker ?? AppPageExperienceTracker.instance;

  @override
  void initState() {
    super.initState();
    _shownAt = DateTime.now();
    _scheduleShownOutcome();
  }

  @override
  void didUpdateWidget(covariant AppPageErrorState oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_telemetryIdentity(oldWidget.semantic) ==
        _telemetryIdentity(widget.semantic)) {
      return;
    }
    _shownAt = DateTime.now();
    _scheduleShownOutcome();
  }

  void _scheduleShownOutcome() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final semantic = widget.semantic;
      unawaited(
        _experienceTracker.recordFirstUsable(
          terminal: AppPageUsableTerminal.error,
          surfaceId: semantic.sourceSurfaceId ?? semantic.sourceRouteId,
          failReasonCode: semantic.sourceCode,
        ),
      );
      _enqueueErrorOutcome(semantic: semantic, result: 'shown', durationMs: 0);
    });
  }

  Future<void> _handleAction(UiErrorAction action) async {
    final callback = widget.onAction;
    if (callback == null) {
      return;
    }
    final semantic = widget.semantic;
    _enqueueErrorOutcome(
      semantic: semantic,
      result: 'recovery_started',
      action: action,
    );
    try {
      await callback(action);
      _enqueueErrorOutcome(
        semantic: semantic,
        result: 'recovered',
        action: action,
      );
    } catch (error, stackTrace) {
      _enqueueErrorOutcome(
        semantic: semantic,
        result: 'recovery_failed',
        action: action,
      );
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  void _enqueueErrorOutcome({
    required UiErrorSemantic semantic,
    required String result,
    UiErrorAction? action,
    int? durationMs,
  }) {
    _telemetryTail = _telemetryTail.then(
      (_) => _recordErrorOutcome(
        semantic: semantic,
        result: result,
        action: action,
        durationMs: durationMs,
      ),
    );
  }

  Future<void> _recordErrorOutcome({
    required UiErrorSemantic semantic,
    required String result,
    UiErrorAction? action,
    int? durationMs,
  }) async {
    await _experienceTracker.recordPageErrorOutcome(
      surfaceId: semantic.sourceSurfaceId ?? semantic.sourceRouteId,
      errorCode: semantic.sourceCode,
      recoveryAction: semantic.recoveryAction?.name,
      result: result,
      action: action?.type.name,
      durationMs: durationMs ?? _visibleDurationMs(),
    );
  }

  int _visibleDurationMs() {
    final duration = DateTime.now().difference(_shownAt).inMilliseconds;
    return duration < 0 ? 0 : duration;
  }

  String _telemetryIdentity(UiErrorSemantic semantic) {
    return <String>[
      semantic.sourceCode ?? '',
      semantic.sourceSurfaceId ?? '',
      semantic.sourceRouteId ?? '',
      semantic.recoveryAction?.name ?? '',
      semantic.presentation.name,
    ].join('|');
  }

  @override
  Widget build(BuildContext context) {
    return _wrapWithErrorAppearance(
      context,
      widget.semantic,
      Builder(
        builder: (themedContext) {
          final background = AppColors.iosPageBackground(themedContext);
          final fallbackStyle = TextStyle(
            color: AppColors.iosLabel(themedContext),
            fontSize: AppTypography.iosBody,
            decoration: TextDecoration.none,
          );
          return ColoredBox(
            color: background,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final height = constraints.hasBoundedHeight
                    ? constraints.maxHeight
                    : MediaQuery.sizeOf(themedContext).height;
                return SizedBox(
                  width: double.infinity,
                  height: height,
                  child: DefaultTextStyle(
                    style: fallbackStyle,
                    child: Center(
                      child: Padding(
                        padding:
                            widget.padding ??
                            EdgeInsets.all(AppSpacing.containerMd),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: AppSpacing.feedMaxContentWidth,
                          ),
                          child: _ErrorEmptyPageBody(
                            semantic: widget.semantic,
                            onAction: widget.onAction == null
                                ? null
                                : _handleAction,
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

/// 区块首屏无可用数据时的阻塞错误态。
///
/// 与 [AppSectionErrorCard] 的局部软失败不同，这里不渲染灰色
/// 卡片外框，避免在已经是空白的内容区中再嵌一张“设置卡”。
class AppSectionErrorState extends StatelessWidget {
  const AppSectionErrorState({
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
    return _wrapWithErrorAppearance(
      context,
      semantic,
      Center(
        child: Padding(
          padding: padding ?? EdgeInsets.all(AppSpacing.containerXl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppSpacing.feedMaxContentWidth,
            ),
            child: _ErrorEmptyPageBody(semantic: semantic, onAction: onAction),
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
      child: _ErrorSoftCardBody(
        semantic: semantic,
        onAction: onAction,
        density: AppFormErrorCardDensity.regular,
      ),
    );
  }
}

enum AppFormErrorCardDensity { regular, compact }

/// 与当前表单操作点关联的唯一主错误反馈；不持有路由或焦点控制权。
class AppFormErrorCard extends StatelessWidget {
  const AppFormErrorCard({
    super.key,
    required this.semantic,
    this.onAction,
    this.margin = EdgeInsets.zero,
    this.density = AppFormErrorCardDensity.regular,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final EdgeInsetsGeometry margin;
  final AppFormErrorCardDensity density;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      container: true,
      child: Padding(
        padding: margin,
        child: _InlineErrorMessage(
          semantic: semantic,
          onAction: onAction,
          density: density,
        ),
      ),
    );
  }
}

/// 输入控件下方的字段级错误；调用方负责同步输入边框错误态。
class AppInlineFieldError extends StatelessWidget {
  const AppInlineFieldError({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      container: true,
      child: _InlineErrorMessage(
        semantic: UiErrorSemantic(
          category: UiErrorCategory.validation,
          scope: UiErrorScope.inlineField,
          title: '',
          message: message,
          presentation: UiErrorPresentation.inlineField,
        ),
      ),
    );
  }
}

/// 透明的字段/表单/局部操作错误行。
///
/// 视觉只表达“这是错误”；错误位置、恢复动作和业务语义由调用方的
/// [UiErrorSemantic] 决定，不在这里复制卡片、色块或私有登录分支。
class _InlineErrorMessage extends StatelessWidget {
  const _InlineErrorMessage({
    required this.semantic,
    this.onAction,
    this.density = AppFormErrorCardDensity.regular,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final AppFormErrorCardDensity density;

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final isCompactWidth =
        mediaQuery.size.width <= AppSpacing.compactBreakpoint ||
        mediaQuery.textScaler.scale(1) >= 1.5;
    final action = semantic.primaryAction;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.hairline),
              child: Icon(
                CupertinoIcons.exclamationmark_circle,
                size: AppSpacing.inlineErrorIconSize,
                color: AppColors.errorForeground(context),
              ),
            ),
            const SizedBox(width: AppSpacing.inlineErrorIconTextGap),
            Expanded(
              child: Text(
                semantic.message,
                maxLines: isCompactWidth ? 2 : 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.errorForeground(context),
                  fontSize: AppTypography.inlineError,
                  fontWeight: AppTypography.inlineErrorWeight,
                  height: AppSpacing.textLineHeightBody,
                ),
              ),
            ),
          ],
        ),
        if (action != null && onAction != null) ...<Widget>[
          SizedBox(
            height: density == AppFormErrorCardDensity.compact
                ? AppSpacing.xs
                : AppSpacing.sm,
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(
              AppSpacing.minInteractiveSize,
              AppSpacing.minInteractiveSize,
            ),
            alignment: Alignment.centerLeft,
            onPressed: () => unawaited(onAction!(action)),
            child: Text(
              action.label,
              style: TextStyle(
                color: AppColors.errorForeground(context),
                fontSize: AppTypography.inlineError,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class AppTransientErrorNotice extends StatelessWidget {
  const AppTransientErrorNotice({
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
                if (semantic.primaryAction case final action?
                    when onAction != null) ...<Widget>[
                  SizedBox(width: AppSpacing.sm),
                  CupertinoButton(
                    minimumSize: const Size(
                      AppSpacing.minInteractiveSize,
                      AppSpacing.minInteractiveSize,
                    ),
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: AppSpacing.xs,
                    ),
                    onPressed: () => unawaited(onAction!(action)),
                    child: Text(action.label),
                  ),
                ],
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
        density: AppFormErrorCardDensity.regular,
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
    if (!context.mounted) {
      return;
    }
    await showAppCupertinoDialog<void>(
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
          if (primary != null)
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () {
                Navigator.of(dialogContext).pop();
                if (onAction != null) {
                  unawaited(onAction(primary));
                }
              },
              child: Text(primary.label),
            )
          else if (semantic.secondaryAction == null)
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(UITextConstants.gotIt),
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
              color: AppColors.iosSecondaryLabel(context),
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
    this.density = AppFormErrorCardDensity.regular,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final bool gate;
  final AppFormErrorCardDensity density;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = AppColors.iosSecondaryFill(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.35);
    final accent = _toneAccentColor(context, semantic.tone);
    final titleColor = AppColors.iosLabel(context);
    final messageColor = AppColors.iosSecondaryLabel(context);
    if (density == AppFormErrorCardDensity.compact) {
      return DecoratedBox(
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              Container(
                width: AppSpacing.xs,
                height: AppSpacing.xs,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.72),
                  shape: BoxShape.circle,
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  semantic.message,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: messageColor,
                    height: AppSpacing.textLineHeightFootnote,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }
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
                        color: AppColors.iosSecondaryLabel(context),
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
    final actions = <Widget>[
      if (semantic.secondaryAction != null)
        _buildSecondaryAction(context, semantic.secondaryAction!),
      if (semantic.primaryAction != null)
        _buildPrimaryAction(context, semantic.primaryAction!),
    ];
    if (!compact) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: actions
            .map(
              (action) => Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.intraGroupXs,
                ),
                child: SizedBox(
                  width: AppSpacing.minInteractiveSize * 2.55,
                  height: AppSpacing.minInteractiveSize,
                  child: action,
                ),
              ),
            )
            .toList(growable: false),
      );
    }
    return Wrap(
      alignment: WrapAlignment.start,
      spacing: AppSpacing.containerSm,
      runSpacing: AppSpacing.containerSm,
      children: actions,
    );
  }

  Widget _buildSecondaryAction(BuildContext context, UiErrorAction action) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = isDark
        ? AppColors.white.withValues(alpha: 0.08)
        : CupertinoColors.systemBackground.resolveFrom(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.26 : 0.2);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        border: Border.all(color: border, width: AppSpacing.hairline),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? AppSpacing.sm : AppSpacing.containerMd,
          vertical: compact ? AppSpacing.xs : AppSpacing.sm,
        ),
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        onPressed: _canDispatch(action)
            ? () => unawaited(_dispatchAction(context, action))
            : null,
        child: Center(
          child: Text(
            action.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.iosLabel(context),
              fontWeight: AppTypography.medium,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryAction(BuildContext context, UiErrorAction action) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? AppSpacing.containerSm : AppSpacing.containerMd,
        vertical: compact ? AppSpacing.xs : AppSpacing.sm,
      ),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      color: AppColors.iosTintedFill(context),
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      onPressed: _canDispatch(action)
          ? () => unawaited(_dispatchAction(context, action))
          : null,
      child: Center(
        child: Text(
          action.label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: AppColors.iosAccent(context),
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
    );
  }

  Future<void> _dispatchAction(
    BuildContext context,
    UiErrorAction action,
  ) async {
    if (onAction == null) {
      return;
    }
    await onAction!(action);
  }

  bool _canDispatch(UiErrorAction action) {
    return onAction != null;
  }
}

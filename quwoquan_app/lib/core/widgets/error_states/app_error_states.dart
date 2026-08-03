import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_terminal_viewport.dart';

import 'app_error_action_feedback.dart';
export 'app_error_action_feedback.dart';
part 'app_error_action_row.dart';
part 'app_error_state_appearance.dart';

class AppPageErrorState extends StatefulWidget {
  const AppPageErrorState({
    super.key,
    required this.semantic,
    this.onAction,
    this.onRecovery,
    this.padding,
    this.experienceTracker,
  }) : assert(
         onAction == null || onRecovery == null,
         'Use the typed onRecovery callback for page recovery, not both.',
       );

  final UiErrorSemantic semantic;

  /// 存量非阻塞页面的动作回调；新增页面恢复必须使用 [onRecovery]。
  final UiErrorActionCallback? onAction;
  final UiRecoveryActionCallback? onRecovery;
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
    final callback = widget.onRecovery;
    final legacyCallback = widget.onAction;
    if (callback == null && legacyCallback == null) {
      return;
    }
    final semantic = widget.semantic;
    _enqueueErrorOutcome(
      semantic: semantic,
      result: 'recovery_started',
      action: action,
    );
    try {
      final outcome = callback != null
          ? await callback(action)
          : await _runLegacyAction(legacyCallback!, action);
      _enqueueErrorOutcome(
        semantic: semantic,
        result: switch (outcome) {
          UiRecoveryOutcome.recovered => 'recovered',
          UiRecoveryOutcome.stillBlocked => 'still_blocked',
          UiRecoveryOutcome.handedOff => 'handed_off',
          UiRecoveryOutcome.superseded => 'superseded',
          UiRecoveryOutcome.cancelled => 'cancelled',
        },
        action: action,
      );
    } catch (error, stackTrace) {
      _enqueueErrorOutcome(
        semantic: semantic,
        result: 'recovery_unexpected_failure',
        action: action,
      );
      developer.log(
        'Unexpected page recovery callback failure.',
        name: 'AppPageErrorState',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<UiRecoveryOutcome> _runLegacyAction(
    UiErrorActionCallback callback,
    UiErrorAction action,
  ) async {
    await callback(action);
    // Future<void> 无法证明页面是否真的离开错误态；只有 typed callback
    // 明确返回 recovered 才允许记录恢复成功。
    return UiRecoveryOutcome.handedOff;
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
            child: DefaultTextStyle(
              style: fallbackStyle,
              child: AppTerminalViewport(
                padding:
                    widget.padding ?? EdgeInsets.all(AppSpacing.containerMd),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.feedMaxContentWidth,
                  ),
                  child: _ErrorEmptyPageBody(
                    semantic: widget.semantic,
                    onAction:
                        widget.onAction == null && widget.onRecovery == null
                        ? null
                        : _handleAction,
                  ),
                ),
              ),
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
      LayoutBuilder(
        builder: (context, constraints) {
          final resolvedPadding =
              (padding ?? EdgeInsets.all(AppSpacing.containerXl)).resolve(
                Directionality.of(context),
              );
          final content = Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppSpacing.feedMaxContentWidth,
              ),
              child: _ErrorEmptyPageBody(
                semantic: semantic,
                onAction: onAction,
              ),
            ),
          );
          if (!constraints.hasBoundedHeight) {
            return Padding(padding: resolvedPadding, child: content);
          }
          final availableHeight =
              constraints.maxHeight - resolvedPadding.vertical;
          return SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: resolvedPadding,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: availableHeight > 0 ? availableHeight : 0,
              ),
              child: content,
            ),
          );
        },
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
        Text(
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
        density: AppFormErrorCardDensity.regular,
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
    return Semantics(
      container: true,
      liveRegion: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
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
          if (onAction != null &&
              (semantic.primaryAction != null ||
                  semantic.secondaryAction != null)) ...<Widget>[
            SizedBox(height: AppSpacing.interGroupMd),
            _ErrorActionRow(semantic: semantic, onAction: onAction),
          ],
        ],
      ),
    );
  }
}

class _ErrorSoftCardBody extends StatelessWidget {
  const _ErrorSoftCardBody({
    required this.semantic,
    this.onAction,
    this.density = AppFormErrorCardDensity.regular,
  });

  final UiErrorSemantic semantic;
  final UiErrorActionCallback? onAction;
  final AppFormErrorCardDensity density;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = AppColors.iosSecondaryFill(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.35);
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
    );
  }
}

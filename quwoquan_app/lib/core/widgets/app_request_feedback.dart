import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

enum _AppRequestFeedbackPlacement { page, section, inline, progress }

/// 等待反馈只负责进度位置、慢提示和无障碍；不取数、不持有业务终态。
class AppRequestFeedback extends StatelessWidget {
  const AppRequestFeedback._(
    this._placement, {
    super.key,
    required this.showSlowHint,
    required this.showIndicator,
    required this.loadingLabel,
    required this.slowLabel,
    this.progress,
    this.indicatorColor,
  });

  factory AppRequestFeedback.page({
    Key? key,
    bool showSlowHint = false,
    bool showIndicator = true,
    String loadingLabel = FoundationText.loading,
    String slowLabel = FoundationText.requestWaitSlow,
  }) {
    return AppRequestFeedback._(
      _AppRequestFeedbackPlacement.page,
      key: key,
      showSlowHint: showSlowHint,
      showIndicator: showIndicator,
      loadingLabel: loadingLabel,
      slowLabel: slowLabel,
    );
  }

  factory AppRequestFeedback.section({
    Key? key,
    bool showSlowHint = false,
    bool showIndicator = true,
    String loadingLabel = FoundationText.loading,
    String slowLabel = FoundationText.requestWaitSlow,
  }) {
    return AppRequestFeedback._(
      _AppRequestFeedbackPlacement.section,
      key: key,
      showSlowHint: showSlowHint,
      showIndicator: showIndicator,
      loadingLabel: loadingLabel,
      slowLabel: slowLabel,
    );
  }

  factory AppRequestFeedback.inline({
    Key? key,
    bool showSlowHint = false,
    bool showIndicator = true,
    String loadingLabel = FoundationText.loading,
    String slowLabel = FoundationText.requestActionSlow,
    Color? indicatorColor,
  }) {
    return AppRequestFeedback._(
      _AppRequestFeedbackPlacement.inline,
      key: key,
      showSlowHint: showSlowHint,
      showIndicator: showIndicator,
      loadingLabel: loadingLabel,
      slowLabel: slowLabel,
      indicatorColor: indicatorColor,
    );
  }

  factory AppRequestFeedback.progress({
    Key? key,
    required double progress,
    String loadingLabel = FoundationText.loading,
    String? stageLabel,
  }) {
    final normalizedProgress = progress.clamp(0.0, 1.0).toDouble();
    final normalizedStage = stageLabel?.trim() ?? '';
    return AppRequestFeedback._(
      _AppRequestFeedbackPlacement.progress,
      key: key,
      showSlowHint: true,
      showIndicator: true,
      loadingLabel: loadingLabel,
      slowLabel: normalizedStage.isNotEmpty
          ? normalizedStage
          : '${(normalizedProgress * 100).round()}%',
      progress: normalizedProgress,
    );
  }

  final _AppRequestFeedbackPlacement _placement;
  final bool showSlowHint;
  final bool showIndicator;
  final String loadingLabel;
  final String slowLabel;
  final double? progress;
  final Color? indicatorColor;

  @override
  Widget build(BuildContext context) {
    final disableAnimations = MediaQuery.disableAnimationsOf(context);
    final isContentPlaceholder =
        _placement == _AppRequestFeedbackPlacement.page ||
        _placement == _AppRequestFeedbackPlacement.section;
    final indicator = progress != null
        ? CupertinoActivityIndicator.partiallyRevealed(progress: progress!)
        : isContentPlaceholder
        ? _AppRequestPlaceholder(
            compact: _placement == _AppRequestFeedbackPlacement.section,
            animate: !disableAnimations,
          )
        : CupertinoActivityIndicator(
            animating: !disableAnimations,
            color: indicatorColor,
          );
    final inlineIndicator = SizedBox.square(
      dimension: AppSpacing.iconSmall,
      child: FittedBox(child: indicator),
    );
    final feedback = _placement == _AppRequestFeedbackPlacement.inline
        ? showSlowHint
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    if (showIndicator)
                      Flexible(fit: FlexFit.loose, child: inlineIndicator),
                    if (showIndicator) SizedBox(width: AppSpacing.intraGroupSm),
                    Flexible(child: _message(context)),
                  ],
                )
              : showIndicator
              ? inlineIndicator
              : const SizedBox.shrink()
        : Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (showIndicator) indicator,
              if (showSlowHint) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupSm),
                _message(context),
              ],
            ],
          );

    final padded = switch (_placement) {
      _AppRequestFeedbackPlacement.page => Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: feedback,
        ),
      ),
      _AppRequestFeedbackPlacement.section => Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerLg),
        child: Center(child: feedback),
      ),
      _AppRequestFeedbackPlacement.inline ||
      _AppRequestFeedbackPlacement.progress => feedback,
    };

    return Semantics(
      container: true,
      liveRegion: showSlowHint,
      label: showSlowHint ? slowLabel : loadingLabel,
      child: ExcludeSemantics(child: padded),
    );
  }

  Widget _message(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Text(
      slowLabel,
      textAlign: TextAlign.center,
      style: TextStyle(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundSecondary,
        ),
        fontSize: AppTypography.iosFootnote,
      ),
    );
  }
}

class _AppRequestPlaceholder extends StatefulWidget {
  const _AppRequestPlaceholder({required this.compact, required this.animate});

  final bool compact;
  final bool animate;

  @override
  State<_AppRequestPlaceholder> createState() => _AppRequestPlaceholderState();
}

class _AppRequestPlaceholderState extends State<_AppRequestPlaceholder>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
    lowerBound: 0.48,
    upperBound: 0.82,
    value: widget.animate ? 0.48 : 0.62,
  );

  @override
  void initState() {
    super.initState();
    if (widget.animate) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(covariant _AppRequestPlaceholder oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.animate == widget.animate) return;
    if (widget.animate) {
      _controller.repeat(reverse: true);
    } else {
      _controller.stop();
      _controller.value = 0.62;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final baseColor = AppColors.iosSecondaryFill(context);
    final widths = widget.compact
        ? const <double>[168, 112]
        : const <double>[228, 196, 144];
    return FadeTransition(
      opacity: _controller,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (var index = 0; index < widths.length; index++) ...<Widget>[
            Container(
              key: ValueKey<String>('app-request-placeholder-$index'),
              width: widths[index],
              height: index == 0 ? AppSpacing.containerSm : AppSpacing.sm,
              decoration: BoxDecoration(
                color: baseColor,
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
              ),
            ),
            if (index < widths.length - 1)
              SizedBox(height: AppSpacing.intraGroupSm),
          ],
        ],
      ),
    );
  }
}

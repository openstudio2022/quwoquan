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
  });

  factory AppRequestFeedback.page({
    Key? key,
    bool showSlowHint = false,
    bool showIndicator = true,
    String loadingLabel = UITextConstants.loading,
    String slowLabel = UITextConstants.requestWaitSlow,
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
    String loadingLabel = UITextConstants.loading,
    String slowLabel = UITextConstants.requestWaitSlow,
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
    String loadingLabel = UITextConstants.loading,
    String slowLabel = UITextConstants.requestActionSlow,
  }) {
    return AppRequestFeedback._(
      _AppRequestFeedbackPlacement.inline,
      key: key,
      showSlowHint: showSlowHint,
      showIndicator: showIndicator,
      loadingLabel: loadingLabel,
      slowLabel: slowLabel,
    );
  }

  factory AppRequestFeedback.progress({
    Key? key,
    required double progress,
    String loadingLabel = UITextConstants.loading,
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

  @override
  Widget build(BuildContext context) {
    final disableAnimations = MediaQuery.disableAnimationsOf(context);
    final indicator = progress == null
        ? CupertinoActivityIndicator(animating: !disableAnimations)
        : CupertinoActivityIndicator.partiallyRevealed(progress: progress!);
    final feedback = _placement == _AppRequestFeedbackPlacement.inline
        ? Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (showIndicator) indicator,
              if (showSlowHint) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupSm),
                Flexible(child: _message(context)),
              ],
            ],
          )
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

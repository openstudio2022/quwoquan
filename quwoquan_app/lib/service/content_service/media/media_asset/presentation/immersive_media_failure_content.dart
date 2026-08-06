import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 沉浸媒体失败态的纯展示模型。
///
/// 宿主必须先完成失败分类与恢复策略判断；原始异常、URL 与播放器实现细节不得
/// 进入这里，避免不同媒体面显示不一致或泄露内部信息。
@immutable
class MediaFailurePresentation {
  const MediaFailurePresentation({required this.title, this.message});

  final String title;
  final String? message;

  String get semanticLabel {
    final detail = message?.trim() ?? '';
    return detail.isEmpty ? title : '$title，$detail';
  }
}

/// Work Browser 图片与视频共用的无图标失败内容。
///
/// 背景、封面和页面纹理仍由调用方拥有；本组件只负责内容层、可访问性和文字重试
/// 操作，因此不会进入 ImageBook 的翻页纹理链。
class ImmersiveMediaFailureContent extends StatelessWidget {
  const ImmersiveMediaFailureContent({
    super.key,
    required this.presentation,
    this.retrying = false,
    this.onRetry,
    this.retryKey,
    this.actionLabel = SearchText.reload,
  });

  final MediaFailurePresentation presentation;
  final bool retrying;
  final VoidCallback? onRetry;
  final Key? retryKey;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    final title = presentation.title.trim();
    final message = presentation.message?.trim() ?? '';
    final showRetry = onRetry != null;
    return Semantics(
      container: true,
      liveRegion: true,
      label: presentation.semanticLabel,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.92),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
            ),
          ),
          if (message.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.white.withValues(alpha: 0.72),
                fontSize: AppTypography.xs,
              ),
            ),
          ],
          if (showRetry) ...<Widget>[
            const SizedBox(height: AppSpacing.interGroupSm),
            CupertinoButton(
              key: retryKey,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.xs,
              ),
              color: AppColors.white.withValues(alpha: 0.20),
              disabledColor: AppColors.white.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              onPressed: retrying ? null : onRetry,
              child: retrying
                  ? AppRequestFeedback.inline(indicatorColor: AppColors.white)
                  : Text(
                      actionLabel,
                      style: TextStyle(
                        color: AppColors.white,
                        fontSize: AppTypography.sm,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
            ),
          ],
        ],
      ),
    );
  }
}

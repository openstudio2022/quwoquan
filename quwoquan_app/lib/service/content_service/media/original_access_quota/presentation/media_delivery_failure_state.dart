import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 私有媒体交付判否的终态呈现（DEC-033）。
///
/// 判否收缩用户可见路径时必须给出终态，而不是静默空白——空白会把「换签失败」
/// 伪装成「这里本来就没有图」，用户与 UAT 都无法发现。
///
/// 恢复动作是否在场由调用方决定，因为两类判否的可恢复性不同：
/// - grant 兑换/换签失败可恢复，交出 [onRetry]，用户可主动重试；
/// - 投影声明为私有交付却没给资产身份属自相矛盾，重试不会让资产身份出现，
///   因此不给恢复动作，只呈现失败。
///
/// 文案只描述当前状态，不断言媒体不存在——失败原因是换签未成功。紧凑判据与
/// 视觉规格对齐设计系统既有失败件（AppCachedNetworkImage），避免两套观感。
class MediaDeliveryFailureState extends StatelessWidget {
  const MediaDeliveryFailureState({super.key, this.onRetry, this.message});

  /// 恢复动作。缺席即该判否不可由用户重试消解。
  final VoidCallback? onRetry;

  /// 终态文案。缺席时用私有图片交付失败的缺省措辞。
  ///
  /// 判否原因不同则文案必须不同：把「视频暂无播放通道」说成「图片打不开」
  /// 会让用户按错误的方向自救。
  final String? message;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // 紧凑位（如头像）容不下文案，只呈现图标；终态可见性优先于文案完整性，
        // 恢复动作仍可点击。
        final isCompact =
            constraints.maxHeight.isFinite &&
            constraints.maxHeight < AppSpacing.forty;
        final surface = Container(
          color: AppColors.iosGroupedSurface(context),
          child: Center(
            child: isCompact
                ? _icon(context, AppSpacing.iconSmall)
                : _labeled(context),
          ),
        );
        if (onRetry == null) {
          return surface;
        }
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onRetry,
          child: surface,
        );
      },
    );
  }

  Widget _icon(BuildContext context, double size) {
    return Icon(
      // 可重试与不可重试用不同图标：前者提示还有出路，后者与公开图失败同形。
      onRetry == null ? Icons.image_not_supported_outlined : Icons.refresh,
      color: AppColors.iosSecondaryLabel(context),
      size: size,
    );
  }

  Widget _labeled(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _icon(context, AppSpacing.twenty),
        const SizedBox(height: AppSpacing.xs),
        Text(
          message ?? MediaText.signedDeliveryFailedMessage,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.iosCaption1,
          ),
        ),
        if (onRetry != null)
          Text(
            MediaText.signedDeliveryRetryAction,
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.iosAccent(context),
              fontSize: AppTypography.iosCaption1,
            ),
          ),
      ],
    );
  }
}

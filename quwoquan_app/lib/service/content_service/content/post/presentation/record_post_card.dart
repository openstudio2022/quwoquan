import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_cover_slot.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/runtime/di/content_post_media_binding.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/design_system/media/content_preview_card.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

typedef PostIntersectionReasonSlotBuilder = Widget? Function(
  List<IntersectionReason>? reasons, {
  required bool isDark,
  required ReferralSource referralSource,
  required String contextObjectName,
  required IntersectionTarget contextObjectTarget,
});

typedef PostLikeCountResolver = int Function(
  WidgetRef ref,
  String postId, {
  required int fallback,
});

/// 统一记录卡（用户主页 / 圈子 / 实体三页共用范式）。
///
/// 结构固定为：封面 + 唯一交集句（卡内 header）+ 标题 + 作者 + 点赞数。
/// - 交集句经 [IntersectionReasonChip.fromReasons] 解析，无来源不展示、不占位（G2）。
/// - 作者与点赞下沉为可复用 footer，避免各页重复实现记录卡。
class RecordPostCard extends ConsumerWidget {
  const RecordPostCard({
    super.key,
    required this.post,
    required this.isDark,
    required this.onTap,
    required this.buildIntersectionReason,
    required this.resolveLikeCount,
    required this.referralSource,
    this.showAuthor = true,
  });

  final ContentPostViewData post;
  final bool isDark;
  final VoidCallback onTap;
  final PostIntersectionReasonSlotBuilder buildIntersectionReason;
  final PostLikeCountResolver resolveLikeCount;

  /// 作者位（用户主页主人即自己时可关闭）。
  final bool showAuthor;

  /// 展示面来源渠道（透传给交集句片段点击埋点，精确归因，N5/N10）。
  final ReferralSource referralSource;

  double get _imageAspectRatio {
    final ratio = post.aspectRatio;
    if (ratio != null && ratio > 0) {
      return ratio.clamp(9.0 / 16.0, 16.0 / 9.0);
    }
    if (post.isVideoLike) {
      return 9 / 16;
    }
    if (post.hasVisualMedia) {
      return 3 / 4;
    }
    return 1.0;
  }

  String get _headlineText {
    final title = post.normalizedTitle;
    final body = post.normalizedBody;
    if (title.isNotEmpty) return title;
    if (body.isNotEmpty) return body;
    return ProfileText.profileTabCreations;
  }

  String get _supportingText {
    final title = post.normalizedTitle;
    final body = post.normalizedBody;
    if (title.isEmpty || body.isEmpty || title == body) {
      return '';
    }
    return body;
  }

  String get _intersectionObjectName {
    final title = post.normalizedTitle.trim();
    if (title.isNotEmpty) return title;
    return post.normalizedBody.trim();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final likeCount = resolveLikeCount(ref, post.id, fallback: post.likeCount);
    final metaTextStyle = TextStyle(
      fontSize: AppTypography.iosCaption1,
      color: fgSecondary,
    );
    return ContentPreviewCard(
      isDark: isDark,
      title: _headlineText,
      supportingText: _supportingText,
      coverUrl: post.primaryVisualUrl,
      // 交付形态取自投影 mediaItems 的同一条目（DEC-033），不从 URL 反推。
      mediaContent: mediaDeliveryCoverSlot(
        binding: contentPostMediaBinding(post, post.primaryVisualUrl),
        placeholderColor: fgSecondary.withValues(alpha: 0.12),
      ),
      mediaAspectRatio: _imageAspectRatio,
      showVideoBadge: post.isVideoLike,
      onTap: onTap,
      header: buildIntersectionReason(
        post.intersectionReasons,
        isDark: isDark,
        referralSource: referralSource,
        contextObjectName: _intersectionObjectName,
        contextObjectTarget: IntersectionTarget(
          objectType: 'post',
          objectId: post.id,
          objectKind: 'content',
          routeId: 'workBrowser',
        ),
      ),
      footer: Row(
        children: <Widget>[
          if (showAuthor)
            Expanded(child: _buildAuthor(context, fgSecondary, metaTextStyle))
          else
            const Spacer(),
          SizedBox(width: AppSpacing.intraGroupXs),
          ContentCardMetric(
            icon: CupertinoIcons.heart,
            label: '$likeCount',
            color: fgSecondary,
            textStyle: metaTextStyle,
          ),
        ],
      ),
    );
  }

  Widget _buildAuthor(
    BuildContext context,
    Color fgSecondary,
    TextStyle metaTextStyle,
  ) {
    final name = post.displayName.trim();
    const diameter = AppSpacing.avatarUserXs;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ClipOval(
          child: SizedBox(
            width: diameter,
            height: diameter,
            child: mediaDeliveryImage(
              binding: contentPostAuthorAvatarBinding(post),
              kind: MediaDeliveryKind.avatar,
              width: diameter,
              height: diameter,
              fit: BoxFit.cover,
              absentWidget: ColoredBox(
                color: fgSecondary.withValues(alpha: 0.12),
              ),
              publicBuilder: (context, publicUrl) => AppAvatarImage(
                imageUrl: publicUrl,
                size: diameter,
                fit: BoxFit.cover,
                placeholder: ColoredBox(
                  color: fgSecondary.withValues(alpha: 0.12),
                ),
                errorWidget: ColoredBox(
                  color: fgSecondary.withValues(alpha: 0.12),
                ),
              ),
            ),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        Flexible(
          child: Text(
            name.isEmpty ? ProfileText.profileTabCreations : name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: metaTextStyle,
          ),
        ),
      ],
    );
  }
}

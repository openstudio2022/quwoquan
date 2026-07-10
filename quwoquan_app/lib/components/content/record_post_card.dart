import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/interactions/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/components/content/intersection_reason_chip.dart';

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
    this.showAuthor = true,
    this.referralSource,
  });

  final PostBaseDto post;
  final bool isDark;
  final VoidCallback onTap;

  /// 作者位（用户主页主人即自己时可关闭）。
  final bool showAuthor;

  /// 展示面来源渠道（透传给交集句片段点击埋点，精确归因，N5/N10）。
  final ReferralSource? referralSource;

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
    return UITextConstants.profileTabCreations;
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
    ref.watch(postInteractionStateProvider);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final likeCount = effectivePostLikeCount(
      ref,
      post.id,
      fallback: post.likeCount,
    );
    final metaTextStyle = TextStyle(
      fontSize: AppTypography.iosCaption1,
      color: fgSecondary,
    );
    return PostPreviewCard(
      isDark: isDark,
      title: _headlineText,
      supportingText: _supportingText,
      coverUrl: post.primaryVisualUrl,
      mediaAspectRatio: _imageAspectRatio,
      showVideoBadge: post.isVideoLike,
      onTap: onTap,
      header: IntersectionReasonChip.fromReasons(
        post.intersectionReasons,
        isDark: isDark,
        referralSource: referralSource,
        contextObjectName: _intersectionObjectName,
        contextObjectTarget: IntersectionTarget(
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
          PostCardMetric(
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
    final avatar = post.avatarUrl.trim();
    const diameter = AppSpacing.avatarUserXs;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ClipOval(
          child: SizedBox(
            width: diameter,
            height: diameter,
            child: avatar.isEmpty
                ? ColoredBox(color: fgSecondary.withValues(alpha: 0.12))
                : AppAvatarImage(
                    imageUrl: avatar,
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
        SizedBox(width: AppSpacing.intraGroupXs),
        Flexible(
          child: Text(
            name.isEmpty ? UITextConstants.profileTabCreations : name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: metaTextStyle,
          ),
        ),
      ],
    );
  }
}

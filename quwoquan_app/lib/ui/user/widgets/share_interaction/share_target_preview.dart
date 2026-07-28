import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';

class ShareTargetPreview extends StatelessWidget {
  const ShareTargetPreview({super.key, required this.item, this.onTap});

  final ShareInteractionItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: ValueKey<String>('share-target-preview-${item.interactionId}'),
      minimumSize: const Size(
        AppSpacing.profileShareInteractionPreviewSize,
        AppSpacing.profileShareInteractionPreviewSize,
      ),
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        child: SizedBox.square(
          dimension: AppSpacing.profileShareInteractionPreviewSize,
          child: _buildContent(context),
        ),
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    if (item.previewKind == SharePreviewKind.unavailable) {
      return _TextPreview(text: _unavailableText(item.targetAvailability));
    }
    if (item.previewKind == SharePreviewKind.image ||
        item.previewKind == SharePreviewKind.video) {
      if (item.previewImageUrl.trim().isEmpty) {
        return _TextPreview(
          text: item.previewKind == SharePreviewKind.video
              ? ProfileText.profileShareVideo
              : ProfileText.profileShareImageUnavailable,
        );
      }
      return Stack(
        fit: StackFit.expand,
        children: <Widget>[
          AppCachedNetworkImage(
            imageUrl: item.previewImageUrl,
            fit: BoxFit.cover,
            errorWidget: _TextPreview(
              text: item.previewKind == SharePreviewKind.video
                  ? ProfileText.profileShareVideo
                  : ProfileText.profileShareImageUnavailable,
            ),
          ),
          if (item.previewKind == SharePreviewKind.video)
            Center(
              child: Icon(
                CupertinoIcons.play_fill,
                size: AppSpacing.iconSmall,
                color: AppColors.white,
              ),
            ),
        ],
      );
    }
    final text = item.previewKind == SharePreviewKind.discussion
        ? _discussionText(item)
        : _firstText(item.previewText, item.targetSummary);
    return _TextPreview(text: text);
  }
}

class _TextPreview extends StatelessWidget {
  const _TextPreview({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundSecondary,
        ),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.xs),
        child: Center(
          child: Text(
            text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

String _discussionText(ShareInteractionItem item) {
  final summary = _firstText(item.targetSummary, item.previewText);
  if (item.targetReplyCount <= 0) return summary;
  return '$summary · ${item.targetReplyCount}${ProfileText.profileShareDiscussionRepliesSuffix}';
}

String _unavailableText(ShareTargetAvailability availability) {
  return switch (availability) {
    ShareTargetAvailability.deleted => ProfileText.profileShareDeleted,
    ShareTargetAvailability.private => ProfileText.profileSharePrivate,
    ShareTargetAvailability.reviewing => ProfileText.profileShareReviewing,
    ShareTargetAvailability.authorDeactivated =>
      ProfileText.profileShareAuthorDeactivated,
    ShareTargetAvailability.active =>
      ProfileText.profileInteractionPreviewUnavailable,
  };
}

String _firstText(String first, String second) {
  if (first.trim().isNotEmpty) return first.trim();
  if (second.trim().isNotEmpty) return second.trim();
  return ProfileText.profileInteractionPreviewUnavailable;
}

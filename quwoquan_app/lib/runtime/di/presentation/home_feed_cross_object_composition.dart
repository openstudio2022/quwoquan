import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_viewer_modal.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_center_glyph.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_action_keys.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/home_intersection_spotlight_rail.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/immersive_intersection_statement.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Runtime composition for the Post feed's Comment, Media and Recommendation
/// participants. The feed retains physical ownership while concrete sibling
/// presentation dependencies are assembled at the composition root.
abstract final class HomeFeedCrossObjectComposition {
  static Widget intersectionSpotlight({
    required bool isDark,
    required String channelId,
  }) {
    return HomeIntersectionSpotlightRail(isDark: isDark, channelId: channelId);
  }

  static Widget interactiveIntersectionText({
    required List<IntersectionTextSpan> spans,
    required String fallbackText,
    void Function(IntersectionTextSpan span)? onSpanTap,
    VoidCallback? onFallbackTap,
    TextStyle? baseStyle,
    FontWeight? accentFontWeight,
    int maxLines = 1,
  }) {
    return InteractiveIntersectionText(
      spans: spans,
      fallbackText: fallbackText,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
      baseStyle: baseStyle,
      accentFontWeight: accentFontWeight ?? FontWeight.w400,
      maxLines: maxLines,
    );
  }

  static bool isGatheringAction(String actionKey) {
    return IntersectionActionKeys.isGatheringAction(actionKey);
  }

  static IntersectionReason? displayReadyIntersection(
    IntersectionReason reason, {
    IntersectionTarget? contextObjectTarget,
  }) {
    return displayReadyIntersectionReason(
      reason,
      contextObjectTarget: contextObjectTarget,
    );
  }

  static Widget immersiveIntersectionStatement({
    Key? key,
    required IntersectionReason reason,
    required String contextObjectName,
    IntersectionTarget? contextObjectTarget,
    void Function(IntersectionTextSpan span)? onSpanTap,
    VoidCallback? onFallbackTap,
    void Function(IntersectionActionHint hint)? onActionHintTap,
  }) {
    return ImmersiveIntersectionStatement(
      key: key,
      reason: reason,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
      onActionHintTap: onActionHintTap,
    );
  }

  static Future<void> showComments({
    required BuildContext context,
    required String postId,
    int? entryObservedCommentCount,
    VoidCallback? onShareTap,
  }) {
    return CommentViewer.showModal(
      context: context,
      postId: postId,
      entryObservedCommentCount: entryObservedCommentCount,
      onShareTap: onShareTap,
    );
  }

  static Widget immersiveCommentSplit({
    required String postId,
    required Widget content,
    required int entryObservedCommentCount,
    required MediaViewerCommentContext commentContext,
    required int likeCount,
    required int shareCount,
    required bool isLiked,
    required VoidCallback onLikeTap,
    required VoidCallback onShareTap,
    required VoidCallback onClose,
  }) {
    return ImmersiveCommentSplitSheet(
      postId: postId,
      content: content,
      entryObservedCommentCount: entryObservedCommentCount,
      commentContext: commentContext,
      likeCount: likeCount,
      shareCount: shareCount,
      isLiked: isLiked,
      onLikeTap: onLikeTap,
      onShareTap: onShareTap,
      onClose: onClose,
    );
  }

  static Widget videoPlayer({
    Key? key,
    MediaDeliveryReference? deliveryReference,
    SignedVideoDelivery? signedDelivery,
    MediaDeliveryReference? adaptiveDeliveryReference,
    int adaptiveDescriptorVersion = 0,
    MediaDeliveryBinding thumbnailBinding = const MediaDeliveryBinding.absent(),
    required bool initialize,
    required bool autoPlay,
    required bool inlineOverlay,
    Duration? verifiedDuration,
    double? aspectRatio,
    VoidCallback? onTap,
    void Function(Duration startupLatency, int candidateIndex)?
    onPlaybackStarted,
    ValueChanged<VideoEffectivePlaybackEvidence>? onEffectivePlayback,
    ValueChanged<MediaPlaybackFailure>? onPlaybackFailed,
  }) {
    return VideoPlayerWidget(
      key: key,
      deliveryReference: deliveryReference,
      signedDelivery: signedDelivery,
      adaptiveDeliveryReference: adaptiveDeliveryReference,
      adaptiveDescriptorVersion: adaptiveDescriptorVersion,
      thumbnailBinding: thumbnailBinding,
      initialize: initialize,
      autoPlay: autoPlay,
      showControls: false,
      overlayMode: inlineOverlay
          ? VideoPlaybackOverlayMode.inlineFeed
          : VideoPlaybackOverlayMode.none,
      verifiedDuration: verifiedDuration,
      aspectRatio: aspectRatio,
      onTap: onTap,
      onPlaybackStarted: onPlaybackStarted,
      onEffectivePlayback: onEffectivePlayback,
      onPlaybackFailed: onPlaybackFailed,
    );
  }

  static Widget videoCenterPlayGlyph() {
    return const VideoPlaybackCenterPlayGlyph();
  }
}

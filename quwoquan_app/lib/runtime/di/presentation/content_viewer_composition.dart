import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/shell/shell_immersive_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/presentation/assistant_half_sheet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/single_post_media_viewer.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/unified_media_viewer_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Runtime composition for content surfaces that participate in more than one
/// business object. Object-owned presentation code only sees public values and
/// callbacks; concrete cross-object widgets stay at the composition root.
abstract final class ContentViewerComposition {
  /// featuredWorks 与统一媒体路由共用同一主壳隐藏租约。
  static VoidCallback acquirePureMediaNavigation(WidgetRef ref) =>
      ref.read(bottomNavHiddenProvider.notifier).acquireMediaHidden();
  static Widget featuredWorks({
    bool isActive = true,
    required double topChromeSafeInset,
    required void Function(
      String userId, {
      String? avatarUrl,
      String? avatarAssetId,
      MediaDeliveryAccessMode? avatarAccessMode,
      String? displayName,
      String? backgroundUrl,
    })
    onUserTap,
    required VoidCallback onAssistantTap,
    required VoidCallback onTapBack,
    required VoidCallback onSwitchToFollowing,
    required VoidCallback onSwitchToCircles,
  }) {
    return WorksImmersiveViewer(
      isActive: isActive,
      showWorksToolbar: true,
      topChromeSafeInset: topChromeSafeInset,
      onUserTap: onUserTap,
      onAssistantTap: onAssistantTap,
      onTapBack: onTapBack,
      onSwitchToFollowing: onSwitchToFollowing,
      onSwitchToCircles: onSwitchToCircles,
    );
  }

  static Future<void> showAssistantHalfSheet(
    BuildContext context,
    AssistantOpenContext openContext,
  ) {
    return AssistantHalfSheet.show(context, openContext);
  }

  static MediaViewerExtra singlePostExtra(
    WidgetRef ref, {
    required ContentPostDetailPayload detail,
    required ReferralSource referralSource,
    String? feedRequestId,
    MediaViewerCommentContext commentContext =
        const MediaViewerCommentContext(),
  }) {
    return buildSinglePostMediaViewerExtra(
      ref,
      detail: detail,
      referralSource: referralSource,
      feedRequestId: feedRequestId,
      commentContext: commentContext,
    );
  }

  static Widget unifiedMediaViewer(MediaViewerExtra extra) {
    return UnifiedMediaViewerPage(extra: extra);
  }
}

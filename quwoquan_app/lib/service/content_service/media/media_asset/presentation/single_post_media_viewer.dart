import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_state_bridge.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';

/// 由「单帖详情」构造沉浸式浏览器路由参数。
///
/// 直达 / 深链 / 通知统一走这里，避免各入口各自拼装 [MediaViewerExtra]
/// 归因 [source] / [referralSource] / [feedRequestId]
/// 由调用方按入口语义传入，保持推荐归因链完整（R21）。
MediaViewerExtra buildSinglePostMediaViewerExtra(
  WidgetRef ref, {
  required ContentPostDetailPayload detail,
  required String source,
  required ReferralSource referralSource,
  String? feedRequestId,
  MediaViewerCommentContext commentContext = const MediaViewerCommentContext(),
}) {
  final dto = detail.post;
  final raw = detail.mergedArticleWireMap;
  final snapshot = buildMediaViewerInteractionSnapshot(
    posts: <ContentPostViewData>[dto],
    relationshipState: ref.read(userRelationshipStateProvider),
    postInteractionState: ref.read(postInteractionStateProvider),
  );
  return MediaViewerExtra(
    posts: <ContentSurfaceView>[
      ContentSurfaceViewMapper.fromDto(dto, wire: raw),
    ],
    dtoPosts: <ContentPostViewData>[dto],
    initialIndex: 0,
    source: source,
    rawPostsById: <String, MediaViewerPostWireRow>{
      dto.id: MediaViewerPostWireRow.fromDynamicMap(
        Map<String, dynamic>.from(raw),
      ),
    },
    interactionSnapshot: snapshot,
    referralSource: referralSource,
    feedRequestId: feedRequestId,
    commentContext: commentContext,
  );
}

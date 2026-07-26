import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/interactions/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

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
    posts: <PostBaseDto>[dto],
    relationshipState: ref.read(userRelationshipStateProvider),
    postInteractionState: ref.read(postInteractionStateProvider),
  );
  return MediaViewerExtra(
    posts: <ContentSurfaceView>[
      ContentSurfaceViewMapper.fromDto(dto, wire: raw),
    ],
    dtoPosts: <PostBaseDto>[dto],
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

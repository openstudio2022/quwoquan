import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/service/content_service/content/content_reaction/application/public/content_post_reaction_ports.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

/// 测试注入 Content 的窄 Facet。Comment 已从聚合 Repository 彻底拆除，
/// 只有评论用例可显式传入强类型 [commentFacet]。
///
/// 这是测试容器 wiring，不是业务 Repository 聚合或 App 运行时 Provider。
List<Override> mockContentFacetOverrides(
  Object adapter, {
  ContentPostDetailReader? workBrowserDetailReader,
  ContentCommentFacet? commentFacet,
  ContentPostReactionPort? postReactionFacet,
  ContentBehaviorFactAppender? behaviorWriter,
}) {
  return <Override>[
    contentDiscoveryFeedQueryProvider.overrideWithValue(
      adapter as ContentDiscoveryFeedQuery,
    ),
    workBrowserContentPostDetailReaderProvider.overrideWithValue(
      workBrowserDetailReader ?? adapter as ContentPostDetailReader,
    ),
    globalSearchContentPostDetailReaderProvider.overrideWithValue(
      adapter as ContentPostDetailReader,
    ),
    userProfileContentAuthorPostsReaderProvider.overrideWithValue(
      adapter as ContentAuthorPostsReader,
    ),
    contentPostDeleteCommandWriterProvider.overrideWithValue(
      adapter as ContentPostDeleteCommandWriter,
    ),
    contentBehaviorCommandWriterProvider.overrideWithValue(
      behaviorWriter ?? const _TestContentBehaviorFactAppender(),
    ),
    contentPostReactionFacetProvider.overrideWithValue(
      postReactionFacet ?? InMemoryContentPostReactionPort(),
    ),
    contentConfigRepositoryProvider.overrideWithValue(
      adapter as ContentConfigRepository,
    ),
    if (commentFacet != null) ...<Override>[
      workBrowserContentCommentFacetProvider.overrideWithValue(commentFacet),
      profileCommentsContentCommentFacetProvider.overrideWithValue(
        commentFacet,
      ),
    ],
  ];
}

final class _TestContentBehaviorFactAppender
    implements ContentBehaviorFactAppender {
  const _TestContentBehaviorFactAppender();

  @override
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command) async {}
}

final class InMemoryContentPostReactionPort implements ContentPostReactionPort {
  final Map<String, bool> _liked = <String, bool>{};

  Object? throwOnCommand;
  int commandCallCount = 0;

  @override
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  ) async {
    final liked = _liked[query.postId] ?? false;
    return ContentReactionStateSlice(
      found: _liked.containsKey(query.postId),
      postId: query.postId,
      liked: liked,
      version: liked ? 1 : 0,
      updatedAt: liked ? DateTime.now().toUtc() : null,
    );
  }

  @override
  Future<ContentReactionCommandResult> likePost(
    LikeContentPostCommand command,
  ) => _change(command.postId, true);

  @override
  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  ) => _change(command.postId, false);

  Future<ContentReactionCommandResult> _change(
    String postId,
    bool liked,
  ) async {
    commandCallCount++;
    final failure = throwOnCommand;
    if (failure != null) throw failure;
    final before = _liked[postId] ?? false;
    _liked[postId] = liked;
    return ContentReactionCommandResult(
      reactionId: 'test_post_reaction_$postId',
      postId: postId,
      version: before == liked ? 1 : 2,
      liked: liked,
      changed: before != liked,
      replayed: false,
    );
  }
}

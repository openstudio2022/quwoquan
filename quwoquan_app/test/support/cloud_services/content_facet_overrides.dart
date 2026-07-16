import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'test_content_post_reaction_facet.dart';

/// 测试注入 Content 的窄 Facet。Comment 已从聚合 Repository 彻底拆除，
/// 只有评论用例可显式传入强类型 [commentFacet]。
///
/// 这是测试容器 wiring，不是业务 Repository 聚合或 App 运行时 Provider。
List<Override> mockContentFacetOverrides(
  MockContentRepository adapter, {
  ContentCommentFacet? commentFacet,
  ContentPostReactionFacet? postReactionFacet,
}) {
  return <Override>[
    contentReadRepositoryProvider.overrideWithValue(adapter),
    workBrowserContentPostDetailReaderProvider.overrideWithValue(adapter),
    globalSearchContentPostDetailReaderProvider.overrideWithValue(adapter),
    userProfileContentAuthorPostsReaderProvider.overrideWithValue(adapter),
    contentWriteRepositoryProvider.overrideWithValue(adapter),
    contentEngagementRepositoryProvider.overrideWithValue(adapter),
    contentPostReactionFacetProvider.overrideWithValue(
      postReactionFacet ?? TestContentPostReactionFacet(),
    ),
    contentConfigRepositoryProvider.overrideWithValue(adapter),
    if (commentFacet != null) ...<Override>[
      workBrowserContentCommentFacetProvider.overrideWithValue(commentFacet),
      profileCommentsContentCommentFacetProvider.overrideWithValue(
        commentFacet,
      ),
    ],
  ];
}

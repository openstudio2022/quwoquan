import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'test_content_post_reaction_facet.dart';
import 'content/mock_content_repository.dart';

/// 测试注入 Content 的窄 Facet。Comment 已从聚合 Repository 彻底拆除，
/// 只有评论用例可显式传入强类型 [commentFacet]。
///
/// 这是测试容器 wiring，不是业务 Repository 聚合或 App 运行时 Provider。
List<Override> mockContentFacetOverrides(
  MockContentRepository adapter, {
  ContentPostDetailReader? workBrowserDetailReader,
  ContentCommentFacet? commentFacet,
  ContentPostReactionFacet? postReactionFacet,
  ContentBehaviorCommandWriter? behaviorWriter,
}) {
  return <Override>[
    contentDiscoveryFeedQueryProvider.overrideWithValue(adapter),
    workBrowserContentPostDetailReaderProvider.overrideWithValue(
      workBrowserDetailReader ?? adapter,
    ),
    globalSearchContentPostDetailReaderProvider.overrideWithValue(adapter),
    userProfileContentAuthorPostsReaderProvider.overrideWithValue(adapter),
    contentPostDeleteCommandWriterProvider.overrideWithValue(adapter),
    contentBehaviorCommandWriterProvider.overrideWithValue(
      behaviorWriter ?? const _TestContentBehaviorCommandWriter(),
    ),
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

final class _TestContentBehaviorCommandWriter
    implements ContentBehaviorCommandWriter {
  const _TestContentBehaviorCommandWriter();

  @override
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command) async {}
}

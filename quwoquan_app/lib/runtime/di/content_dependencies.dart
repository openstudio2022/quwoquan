import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/cloud/remote/content/filter_catalog/filter_catalog_remote.dart';
import 'package:quwoquan_app/content/media/media_upload_session/adapters/content_media_object_uploader.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_remote.dart';
import 'package:quwoquan_app/content/content/outbound_share_fact/adapters/outbound_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/author_impact_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/content_app_config_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/content_behavior_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_delete_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_publication_remote.dart';
import 'package:quwoquan_app/content/trust_safety/report/adapters/report_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/content/content/comment/adapters/comment_facets_remote.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/footprint_query_remote.dart';
import 'package:quwoquan_app/content/content/content_reaction/adapters/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_app/content/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_post_reader.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// content domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum ContentProductionAdapter {
  appConfigQuery,
  authorImpact,
  comment,
  filterCatalog,
  footprint,
  media,
  outboundShare,
  postPublication,
  postReaction,
  reportCommand,
  reportQuery,
}

/// content 读写与缓存图的唯一 production owner。
final class AppProductionContentFacets {
  const AppProductionContentFacets({
    required this.read,
    required this.postDeleteWriter,
    required this.behaviorWriter,
  });

  final ContentReadRepository read;
  final ContentPostDeleteCommandWriter postDeleteWriter;
  final ContentBehaviorCommandWriter behaviorWriter;
}

/// 共享同一 generated adapter 与其缓存层的只读 content facet。
final class AppProductionContentPostReaderFacets {
  const AppProductionContentPostReaderFacets({
    required this.detail,
    required this.authorPosts,
    required this.publicationStatus,
    required this.wishlistState,
  });

  final ContentPostDetailReader detail;
  final ContentAuthorPostsReader authorPosts;
  final ContentPostPublicationStatusReader publicationStatus;
  final ContentEntityWishlistStateReader wishlistState;
}

/// content domain 的唯一 production 装配入口。
final class ContentProductionComposition {
  const ContentProductionComposition._();

  static AppProductionContentFacets contentFacets({
    required GeneratedCloudOperationClient client,
    required ContentDiscoveryFeedInvocationContextFactory invocationContext,
    required ContentPostDeleteInvocationContextFactory deleteInvocationContext,
    required Future<List<String>> Function() blockedKeywordsLoader,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required UserProfileCacheService userProfileCache,
    required CacheTelemetrySink telemetrySink,
  }) {
    final discoveryFeed = RemoteContentDiscoveryFeedQuery(
      client: client,
      invocationContext: invocationContext,
      blockedKeywordsLoader: blockedKeywordsLoader,
    );
    final remote = RemoteContentRepository(discoveryFeedQuery: discoveryFeed);
    final deleteWriter = RemoteContentPostDeleteCommandWriter(
      client: client,
      invocationContext: deleteInvocationContext,
    );
    final behavior = RemoteContentBehaviorCommandAdapter(
      client: client,
      invocationContext: invocationContext,
    );
    final cached = CachedContentRepository(
      readDelegate: remote,
      deleteDelegate: deleteWriter,
      postCache: postCache,
      querySnapshotStore: querySnapshotStore,
      blockedKeywordsLoader: blockedKeywordsLoader,
      userProfileCache: userProfileCache,
      telemetrySink: telemetrySink,
    );
    return AppProductionContentFacets(
      read: cached,
      postDeleteWriter: cached,
      behaviorWriter: behavior,
    );
  }

  static ContentMediaStreamObjectUpload contentMediaObjectUpload({
    required void Function(void Function()) onDispose,
  }) {
    final uploader = RemoteContentMediaObjectUploader();
    onDispose(uploader.dispose);
    return uploader.uploadStream;
  }

  static AppProductionContentPostReaderFacets contentPostReaderFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required UserProfileCacheService userProfileCache,
    required CacheTelemetrySink telemetrySink,
  }) {
    final remote = RemoteContentPostReaderAdapter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    final cached = CachedContentPostReader(
      detailDelegate: remote,
      authorPostsDelegate: remote,
      postCache: postCache,
      querySnapshotStore: querySnapshotStore,
      userProfileCache: userProfileCache,
      telemetrySink: telemetrySink,
    );
    return AppProductionContentPostReaderFacets(
      detail: cached,
      authorPosts: cached,
      publicationStatus: remote,
      wishlistState: remote,
    );
  }

  static T generatedAdapter<T>(
    ContentProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      ContentProductionAdapter.appConfigQuery => RemoteContentAppConfigQuery(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.authorImpact => RemoteAuthorImpactQuery(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.comment => RemoteContentCommentFacet(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.filterCatalog => RemoteFilterCatalogQuery(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.footprint => RemoteFootprintRepository(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.media => RemoteContentMediaFacet(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.outboundShare =>
        RemoteContentOutboundShareAppendWriter(
          client: client,
          invocationContext: context,
        ),
      ContentProductionAdapter.postPublication =>
        RemoteContentPostPublicationWriter(
          client: client,
          invocationContext: context,
        ),
      ContentProductionAdapter.postReaction => RemoteContentPostReactionFacet(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.reportCommand => RemoteContentReportAdapter(
        client: client,
        invocationContext: context,
      ),
      ContentProductionAdapter.reportQuery => RemoteContentReportQueryAdapter(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}

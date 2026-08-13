import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/adapters/profile_interaction_activity_remote.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_read_fact/adapters/profile_interaction_read_fact_remote.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/filter_catalog_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_asset_remote.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/adapters/original_access_quota_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/content_media_object_uploader.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/platform_media_picker_adapter.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_session_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/adapters/outbound_share_remote.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_visit_writer.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/author_impact_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_app_config_remote.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_command_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_delete_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_publication_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_outbox_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_facets_remote.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/footprint_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/adapters/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/platform/media/photo_manager_media_library_gateway.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/cached_content_post_reader.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/cached_content_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

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
  profileInteractionActivity,
  profileInteractionReadFact,
  reportCommand,
  reportQuery,
}

/// content 读写与缓存图的唯一 production owner。
final class AppProductionContentFacets {
  const AppProductionContentFacets({
    required this.feedQuery,
    required this.postDeleteWriter,
    required this.behaviorWriter,
  });

  final ContentDiscoveryFeedQuery feedQuery;
  final ContentPostDeleteCommandWriter postDeleteWriter;
  final ContentBehaviorFactAppender behaviorWriter;
}

/// 共享同一 generated adapter 与其缓存层的只读 content facet。
final class AppProductionContentPostReaderFacets {
  const AppProductionContentPostReaderFacets({
    required this.detail,
    required this.authorPosts,
    required this.publicationStatus,
    required this.wishlistState,
    required this.gatheringPosts,
    required this.gatheringSocialProof,
  });

  final ContentPostDetailReader detail;
  final ContentAuthorPostsReader authorPosts;
  final ContentPostPublicationStatusReader publicationStatus;
  final ContentEntityWishlistStateReader wishlistState;
  final ContentGatheringPostsReader gatheringPosts;
  final ContentGatheringSocialProofReader gatheringSocialProof;
}

final class AppProductionBehaviorRepository {
  AppProductionBehaviorRepository({
    required this.repository,
    required this.onDispose,
  });

  final BehaviorRepository repository;
  final void Function() onDispose;

  void dispose() => onDispose();
}

/// 三个 media 对象的 public facet 组合；generated method 的唯一 owner 仍分别位于
/// 各对象 adapter，本组合只做显式 port 委派。
final class AppProductionContentMediaFacet implements ContentMediaFacet {
  const AppProductionContentMediaFacet({
    required this.upload,
    required this.asset,
    required this.originalAccess,
  });

  final RemoteContentMediaUploadSessionAdapter upload;
  final RemoteContentMediaAssetAdapter asset;
  final ContentMediaOriginalAccessWriter originalAccess;

  @override
  Future<MediaUploadSessionCommandResult> initUpload(
    InitContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => upload.initUpload(command, context);

  @override
  Future<MediaUploadSessionCommandResult> completeUpload(
    CompleteContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => upload.completeUpload(command, context);

  @override
  Future<MediaUploadSessionCommandResult> abortUpload(
    AbortContentMediaUploadCommand command,
    ContentMediaUploadCommandContext context,
  ) => upload.abortUpload(command, context);

  @override
  Future<MediaUploadSessionSlice> getUploadSession(
    GetContentMediaUploadSessionQuery query,
  ) => upload.getUploadSession(query);

  @override
  Future<MediaAssetSlice> getMediaAsset(GetContentMediaAssetQuery query) =>
      asset.getMediaAsset(query);

  @override
  Future<MediaAssetDiscardResult> discardMediaAsset(
    DiscardContentMediaAssetCommand command,
    ContentMediaAssetCommandContext context,
  ) => asset.discardMediaAsset(command, context);

  @override
  Future<MediaCoverSelectionResult> selectAutoCover(
    SelectAutoContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => asset.selectAutoCover(command, context);

  @override
  Future<MediaCoverSelectionResult> selectManualCover(
    SelectManualContentMediaCoverCommand command,
    ContentMediaAssetCommandContext context,
  ) => asset.selectManualCover(command, context);

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => originalAccess.requestOriginalAccess(command);
}

/// content domain 的唯一 production 装配入口。
final class ContentProductionComposition {
  const ContentProductionComposition._();

  static AppProductionBehaviorRepository behaviorRepository({
    required ContentBehaviorFactAppender writer,
    required ActorQueuePartition queuePartition,
    required ActorQueueStorage queueStorage,
    String Function()? feedSessionIdProvider,
  }) {
    final remote = DurableContentBehaviorRepository(
      writer: writer,
      feedSessionIdProvider: feedSessionIdProvider,
      queuePartition: queuePartition,
      queueStorage: queueStorage,
    );
    return AppProductionBehaviorRepository(
      repository: remote,
      onDispose: remote.dispose,
    );
  }

  static IntersectionRepository intersectionRepository({
    required GeneratedCloudOperationClient client,
    required Object myIntersectionsInvocationContext,
    required Object objectIntersectionsInvocationContext,
  }) {
    return RemoteIntersectionRepository(
      client: client,
      myIntersectionsInvocationContext:
          myIntersectionsInvocationContext as dynamic,
      objectIntersectionsInvocationContext:
          objectIntersectionsInvocationContext as dynamic,
    );
  }

  static IntersectionVisitWriter intersectionVisitWriter({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    return RemoteIntersectionVisitWriter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
  }

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
    final deleteWriter = RemoteContentPostDeleteCommandWriter(
      client: client,
      invocationContext: deleteInvocationContext,
    );
    final behavior = RemoteContentBehaviorCommandAdapter(
      client: client,
      invocationContext: invocationContext,
    );
    final cached = CachedContentRepository(
      feedDelegate: discoveryFeed,
      deleteDelegate: deleteWriter,
      postCache: postCache,
      querySnapshotStore: querySnapshotStore,
      blockedKeywordsLoader: blockedKeywordsLoader,
      userProfileCache: userProfileCache,
      telemetrySink: telemetrySink,
    );
    return AppProductionContentFacets(
      feedQuery: cached,
      postDeleteWriter: cached,
      behaviorWriter: behavior,
    );
  }

  static ContentMediaStreamObjectUpload contentMediaObjectUpload({
    required CloudHttpClient client,
    required void Function(void Function()) onDispose,
  }) {
    final uploader = RemoteContentMediaObjectUploader(client: client);
    onDispose(uploader.dispose);
    return uploader.uploadStream;
  }

  static MediaPickerPort mediaPickerPort() {
    return PlatformMediaPickerAdapter(PhotoManagerMediaLibraryGateway());
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
      gatheringPosts: remote,
      gatheringSocialProof: remote,
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
      ContentProductionAdapter.media => AppProductionContentMediaFacet(
        upload: RemoteContentMediaUploadSessionAdapter(
          client: client,
          invocationContext: context,
        ),
        asset: RemoteContentMediaAssetAdapter(
          client: client,
          invocationContext: context,
        ),
        originalAccess: RemoteContentOriginalAccessQuotaWriter(
          client: client,
          invocationContext: context,
        ),
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
      ContentProductionAdapter.profileInteractionActivity =>
        RemoteProfileInteractionActivityQuery(
          client: client,
          invocationContext: context,
        ),
      ContentProductionAdapter.profileInteractionReadFact =>
        RemoteProfileInteractionReadFactWriter(
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

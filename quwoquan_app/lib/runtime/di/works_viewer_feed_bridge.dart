import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentFeedEmptyReason;

class WorksViewerFeedSnapshot {
  const WorksViewerFeedSnapshot({
    required this.items,
    required this.hasMore,
    required this.isLoading,
    this.blockingError,
    this.emptyReason,
    this.appendError,
    this.feedRequestId,
    this.policyDigest,
  });

  final List<ContentPostViewData> items;
  final bool hasMore;
  final bool isLoading;
  final Object? blockingError;
  final ContentFeedEmptyReason? emptyReason;
  final Object? appendError;
  final String? feedRequestId;
  final String? policyDigest;
}

final worksViewerFeedProvider =
    Provider.family<AsyncValue<WorksViewerFeedSnapshot>, String>((
      ref,
      channelId,
    ) {
      return ref
          .watch(discoveryFeedProvider(channelId))
          .whenData(
            (state) => WorksViewerFeedSnapshot(
              items: state.items,
              hasMore: state.hasMore,
              isLoading: state.isLoading,
              blockingError: state.blockingError,
              emptyReason: state.emptyReason,
              appendError: state.appendError,
              feedRequestId: state.feedRequestId,
              policyDigest: state.policyDigest,
            ),
          );
    });

class WorksViewerFeedCommands {
  const WorksViewerFeedCommands(this.ref);

  final Ref ref;

  bool contains(String channelId) {
    return ref.read(discoveryFeedMapProvider).containsKey(channelId);
  }

  Future<DiscoveryFeedLoadResult> load(String channelId, {bool force = false}) {
    return ref
        .read(discoveryFeedMapProvider.notifier)
        .load(channelId, force: force);
  }

  Future<void> appendNextPage(String channelId) {
    return ref
        .read(discoveryFeedMapProvider.notifier)
        .appendNextPage(channelId);
  }

  void removePostLocally(String postId) {
    ref.read(discoveryFeedMapProvider.notifier).removePostLocally(postId);
  }
}

final worksViewerFeedCommandsProvider = Provider<WorksViewerFeedCommands>(
  WorksViewerFeedCommands.new,
);

import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';

final class ShareInteractionBucketKey {
  const ShareInteractionBucketKey({
    required this.personaId,
    required this.direction,
  });

  final String personaId;
  final ShareInteractionDirection direction;

  @override
  bool operator ==(Object other) =>
      other is ShareInteractionBucketKey &&
      other.personaId == personaId &&
      other.direction == direction;

  @override
  int get hashCode => Object.hash(personaId, direction);
}

/// Immutable cross-object read model for one persona/direction bucket.
final class ShareInteractionState {
  const ShareInteractionState({
    this.items = const <ShareInteractionItem>[],
    this.nextCursor,
    this.scrollOffset = 0,
    this.isInitialLoading = false,
    this.isRefreshing = false,
    this.isLoadingMore = false,
    this.lastFetchedAt,
    this.error,
    this.generation = 0,
  });

  final List<ShareInteractionItem> items;
  final String? nextCursor;
  final double scrollOffset;
  final bool isInitialLoading;
  final bool isRefreshing;
  final bool isLoadingMore;
  final DateTime? lastFetchedAt;
  final Object? error;
  final int generation;

  bool get hasMore => nextCursor != null && nextCursor!.isNotEmpty;
  bool get hasCachedItems => items.isNotEmpty;

  ShareInteractionState copyWith({
    List<ShareInteractionItem>? items,
    String? nextCursor,
    double? scrollOffset,
    bool? isInitialLoading,
    bool? isRefreshing,
    bool? isLoadingMore,
    DateTime? lastFetchedAt,
    Object? error,
    int? generation,
    bool clearCursor = false,
    bool clearError = false,
  }) {
    return ShareInteractionState(
      items: items ?? this.items,
      nextCursor: clearCursor ? null : (nextCursor ?? this.nextCursor),
      scrollOffset: scrollOffset ?? this.scrollOffset,
      isInitialLoading: isInitialLoading ?? this.isInitialLoading,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      lastFetchedAt: lastFetchedAt ?? this.lastFetchedAt,
      error: clearError ? null : (error ?? this.error),
      generation: generation ?? this.generation,
    );
  }
}

/// Narrow interaction-list capability; repositories and Riverpod state stay
/// private to ProfileInteractionActivityView.
abstract interface class ShareInteractionController {
  Future<void> ensureLoaded();

  Future<void> refresh({bool background = false});

  Future<void> loadMore();

  void saveScrollOffset(double offset);

  Future<void> markSeen(String interactionId);

  Future<void> markRead(String interactionId);
}

abstract final class ShareInteractionEventNames {
  static const String view = 'share_interaction_view';
  static const String directionChange = 'share_direction_change';
  static const String impression = 'share_interaction_impression';
  static const String open = 'share_interaction_open';
  static const String actorOpen = 'share_actor_open';
  static const String impactOpen = 'share_impact_open';
  static const String refresh = 'share_refresh';
  static const String loadMore = 'share_load_more';
}

abstract interface class ShareInteractionTelemetry {
  static const String source = 'profile_interaction_share';

  void track({
    required String eventName,
    required String personaId,
    required ShareInteractionDirection direction,
    ShareInteractionItem? item,
    String? result,
    bool? cacheHit,
    int? itemCount,
  });
}

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

@immutable
class ShareInteractionBucketKey {
  const ShareInteractionBucketKey({
    required this.subAccountId,
    required this.direction,
  });

  final String subAccountId;
  final ShareInteractionDirection direction;

  @override
  bool operator ==(Object other) =>
      other is ShareInteractionBucketKey &&
      other.subAccountId == subAccountId &&
      other.direction == direction;

  @override
  int get hashCode => Object.hash(subAccountId, direction);
}

@immutable
class ShareInteractionState {
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

class ShareInteractionNotifier extends Notifier<ShareInteractionState> {
  ShareInteractionNotifier(this.key);

  static const Duration cacheTtl = Duration(minutes: 5);
  static const int pageSize = 20;

  final ShareInteractionBucketKey key;
  int _generation = 0;

  @override
  ShareInteractionState build() {
    ref.listen(authSessionControllerProvider, (previous, next) {
      if (previous?.activeSubAccountId != next.activeSubAccountId) {
        _generation += 1;
        state = ShareInteractionState(generation: _generation);
      }
    });
    Future<void>.microtask(ensureLoaded);
    return const ShareInteractionState();
  }

  Future<void> ensureLoaded() async {
    if (!_ownsActiveSubAccount) return;
    final fetchedAt = state.lastFetchedAt;
    final isFresh =
        fetchedAt != null && DateTime.now().difference(fetchedAt) < cacheTtl;
    if (state.items.isNotEmpty) {
      if (!isFresh && !state.isRefreshing) {
        unawaited(refresh(background: true));
      }
      return;
    }
    await _fetchFirstPage(background: false);
  }

  Future<void> refresh({bool background = false}) async {
    if (state.isRefreshing) return;
    await _fetchFirstPage(background: background);
  }

  Future<void> _fetchFirstPage({required bool background}) async {
    if (!_ownsActiveSubAccount) return;
    final requestGeneration = ++_generation;
    state = state.copyWith(
      isInitialLoading: !background && state.items.isEmpty,
      isRefreshing: background || state.items.isNotEmpty,
      generation: requestGeneration,
      clearError: true,
    );
    try {
      final page = await ref
          .read(profileInteractionQueryFacetProvider)
          .listActivities(
            ContentProfileInteractionPageQuery(
              subAccountId: key.subAccountId,
              type: ContentProfileInteractionType.share,
              limit: pageSize,
            ),
            direction: key.direction == ShareInteractionDirection.received
                ? ContentProfileInteractionDirection.received
                : ContentProfileInteractionDirection.sent,
          );
      final items = page.items
          .map(ProfileInteractionActivityViewData.fromContentActivity)
          .map((item) => ShareInteractionItem.fromActivity(item, key.direction))
          .toList(growable: false);
      if (!ref.mounted || requestGeneration != _generation) return;
      state = state.copyWith(
        items: items,
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
        isInitialLoading: false,
        isRefreshing: false,
        lastFetchedAt: DateTime.now(),
        clearError: true,
      );
    } catch (error) {
      if (!ref.mounted || requestGeneration != _generation) return;
      state = state.copyWith(
        isInitialLoading: false,
        isRefreshing: false,
        error: error,
      );
    }
  }

  Future<void> loadMore() async {
    if (!_ownsActiveSubAccount || state.isLoadingMore || !state.hasMore) return;
    final requestGeneration = _generation;
    final cursor = state.nextCursor;
    state = state.copyWith(isLoadingMore: true, clearError: true);
    try {
      final page = await ref
          .read(profileInteractionQueryFacetProvider)
          .listActivities(
            ContentProfileInteractionPageQuery(
              subAccountId: key.subAccountId,
              type: ContentProfileInteractionType.share,
              cursor: cursor,
              limit: pageSize,
            ),
            direction: key.direction == ShareInteractionDirection.received
                ? ContentProfileInteractionDirection.received
                : ContentProfileInteractionDirection.sent,
          );
      if (!ref.mounted || requestGeneration != _generation) return;
      final existing = state.items.map((item) => item.interactionId).toSet();
      final appended = page.items
          .map(ProfileInteractionActivityViewData.fromContentActivity)
          .map((item) => ShareInteractionItem.fromActivity(item, key.direction))
          .where((item) => existing.add(item.interactionId))
          .toList(growable: false);
      state = state.copyWith(
        items: <ShareInteractionItem>[...state.items, ...appended],
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
        isLoadingMore: false,
        lastFetchedAt: DateTime.now(),
        clearError: true,
      );
    } catch (error) {
      if (!ref.mounted || requestGeneration != _generation) return;
      state = state.copyWith(isLoadingMore: false, error: error);
    }
  }

  void saveScrollOffset(double offset) {
    if ((state.scrollOffset - offset).abs() < 0.5) return;
    state = state.copyWith(scrollOffset: offset);
  }

  Future<void> markSeen(String interactionId) async {
    final item = _item(interactionId);
    if (item == null ||
        item.direction != ShareInteractionDirection.received ||
        item.seenAt != null) {
      return;
    }
    await _markState(item, 'seen');
  }

  Future<void> markRead(String interactionId) async {
    final item = _item(interactionId);
    if (item == null ||
        item.direction != ShareInteractionDirection.received ||
        item.readAt != null) {
      return;
    }
    await _markState(item, 'read');
  }

  Future<void> _markState(ShareInteractionItem item, String writeState) async {
    if (!_ownsActiveSubAccount) return;
    final telemetryAction = switch (writeState) {
      'seen' => 'mark_seen',
      'read' => 'mark_read',
      _ => throw ArgumentError.value(writeState, 'writeState'),
    };
    final stopwatch = Stopwatch()..start();
    final now = DateTime.now().toUtc();
    final previousItems = state.items;
    state = state.copyWith(
      items: state.items
          .map(
            (candidate) => candidate.interactionId == item.interactionId
                ? candidate.copyWith(
                    seenAt: candidate.seenAt ?? now,
                    readAt: writeState == 'read'
                        ? (candidate.readAt ?? now)
                        : candidate.readAt,
                  )
                : candidate,
          )
          .toList(growable: false),
      clearError: true,
    );
    try {
      await ref
          .read(profileInteractionReadFactAppendFacetProvider)
          .appendReadFact(
            AppendContentProfileInteractionReadFactCommand(
              subAccountId: key.subAccountId,
              activityId: item.interactionId,
              state: writeState == 'read'
                  ? ContentProfileInteractionReadState.read
                  : ContentProfileInteractionReadState.seen,
            ),
          );
      stopwatch.stop();
      if (!ref.mounted) return;
      await ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'profile_interaction',
            action: telemetryAction,
            pageName: 'profile_interaction_tab',
            targetType: 'profile_interaction_activity',
            targetKey: item.interactionId,
            payload: <String, Object?>{
              'result': 'success',
              'durationMs': stopwatch.elapsedMilliseconds,
            },
          );
    } catch (error) {
      stopwatch.stop();
      if (!ref.mounted) return;
      state = state.copyWith(items: previousItems, error: error);
      await ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'profile_interaction',
            action: telemetryAction,
            pageName: 'profile_interaction_tab',
            targetType: 'profile_interaction_activity',
            targetKey: item.interactionId,
            error: error,
            payload: <String, Object?>{
              'result': 'failure',
              'durationMs': stopwatch.elapsedMilliseconds,
            },
          );
    }
  }

  ShareInteractionItem? _item(String interactionId) {
    for (final item in state.items) {
      if (item.interactionId == interactionId) return item;
    }
    return null;
  }

  bool get _ownsActiveSubAccount =>
      ref.read(authSessionControllerProvider).activeSubAccountId.trim() ==
      key.subAccountId.trim();
}

final shareInteractionProvider =
    NotifierProvider.family<
      ShareInteractionNotifier,
      ShareInteractionState,
      ShareInteractionBucketKey
    >(ShareInteractionNotifier.new);

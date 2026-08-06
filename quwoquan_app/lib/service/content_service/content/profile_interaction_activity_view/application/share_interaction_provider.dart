import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/domain/profile_interaction_activity_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show
        profileInteractionQueryFacetProvider,
        profileInteractionReadFactAppendFacetProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ShareInteractionNotifier extends Notifier<ShareInteractionState>
    implements ShareInteractionController {
  ShareInteractionNotifier(this.key);

  static const Duration cacheTtl = Duration(minutes: 5);
  static const int pageSize = 20;

  final ShareInteractionBucketKey key;
  int _generation = 0;

  @override
  ShareInteractionState build() {
    ref.listen(authSessionControllerProvider, (previous, next) {
      if (previous?.activePersonaId != next.activePersonaId) {
        _generation += 1;
        state = ShareInteractionState(generation: _generation);
      }
    });
    Future<void>.microtask(ensureLoaded);
    return const ShareInteractionState();
  }

  @override
  Future<void> ensureLoaded() async {
    if (!_ownsActivePersona) return;
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

  @override
  Future<void> refresh({bool background = false}) async {
    if (state.isRefreshing) return;
    await _fetchFirstPage(background: background);
  }

  Future<void> _fetchFirstPage({required bool background}) async {
    if (!_ownsActivePersona) return;
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
              personaId: key.personaId,
              type: InteractionActivityType.share,
              limit: pageSize,
            ),
            direction: key.direction == ShareInteractionDirection.received
                ? InteractionDirection.received
                : InteractionDirection.sent,
          );
      final items = page.items
          .map(ProfileInteractionActivityViewData.fromWire)
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

  @override
  Future<void> loadMore() async {
    if (!_ownsActivePersona || state.isLoadingMore || !state.hasMore) return;
    final requestGeneration = _generation;
    final cursor = state.nextCursor;
    state = state.copyWith(isLoadingMore: true, clearError: true);
    try {
      final page = await ref
          .read(profileInteractionQueryFacetProvider)
          .listActivities(
            ContentProfileInteractionPageQuery(
              personaId: key.personaId,
              type: InteractionActivityType.share,
              cursor: cursor,
              limit: pageSize,
            ),
            direction: key.direction == ShareInteractionDirection.received
                ? InteractionDirection.received
                : InteractionDirection.sent,
          );
      if (!ref.mounted || requestGeneration != _generation) return;
      final existing = state.items.map((item) => item.interactionId).toSet();
      final appended = page.items
          .map(ProfileInteractionActivityViewData.fromWire)
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

  @override
  void saveScrollOffset(double offset) {
    if ((state.scrollOffset - offset).abs() < 0.5) return;
    state = state.copyWith(scrollOffset: offset);
  }

  @override
  Future<void> markSeen(String interactionId) async {
    final item = _item(interactionId);
    if (item == null ||
        item.direction != ShareInteractionDirection.received ||
        item.seenAt != null) {
      return;
    }
    await _markState(item, 'seen');
  }

  @override
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
    if (!_ownsActivePersona) return;
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
              personaId: key.personaId,
              activityId: item.interactionId,
              state: writeState == 'read'
                  ? ProfileInteractionReadState.read
                  : ProfileInteractionReadState.seen,
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

  bool get _ownsActivePersona =>
      ref.read(authSessionControllerProvider).activePersonaId.trim() ==
      key.personaId.trim();
}

final shareInteractionProvider =
    NotifierProvider.family<
      ShareInteractionNotifier,
      ShareInteractionState,
      ShareInteractionBucketKey
    >(ShareInteractionNotifier.new);

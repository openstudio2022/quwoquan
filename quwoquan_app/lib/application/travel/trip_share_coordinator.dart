import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_share_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripShareIdempotencyKeyFactory = String Function();

/// 用户选择的分享范围；只描述意图，不复制旅行事实。
final class TripShareSelection {
  const TripShareSelection._({
    required this.scope,
    required this.visibility,
    this.dayIndex,
    this.itemId,
    this.momentIds = const <String>[],
  });

  const TripShareSelection.full({
    TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
  }) : this._(scope: TripShareSnapshotScope.full, visibility: visibility);

  const TripShareSelection.route({
    TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
  }) : this._(scope: TripShareSnapshotScope.route, visibility: visibility);

  const TripShareSelection.day({
    required int dayIndex,
    TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
  }) : this._(
         scope: TripShareSnapshotScope.day,
         visibility: visibility,
         dayIndex: dayIndex,
       );

  const TripShareSelection.item({
    required int dayIndex,
    required String itemId,
    TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
  }) : this._(
         scope: TripShareSnapshotScope.item,
         visibility: visibility,
         dayIndex: dayIndex,
         itemId: itemId,
       );

  TripShareSelection.moments({
    required List<String> momentIds,
    TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
  }) : this._(
         scope: TripShareSnapshotScope.momentCollection,
         visibility: visibility,
         momentIds: List<String>.unmodifiable(momentIds),
       );

  final TripShareSnapshotScope scope;
  final TripShareSnapshotVisibility visibility;
  final int? dayIndex;
  final String? itemId;
  final List<String> momentIds;

  TripShareSelection withVisibility(TripShareSnapshotVisibility value) {
    return TripShareSelection._(
      scope: scope,
      visibility: value,
      dayIndex: dayIndex,
      itemId: itemId,
      momentIds: momentIds,
    );
  }
}

/// 从同一冻结 revision/source digest 生成分享 command，并维持一次意图一个幂等键。
final class TripShareCoordinator {
  const TripShareCoordinator({
    required this.facet,
    required this.idempotencyKeyFactory,
  });

  final TripShareFacet facet;
  final TripShareIdempotencyKeyFactory idempotencyKeyFactory;

  Future<TripShareSnapshot> create(
    TripJourneySnapshot snapshot,
    TripShareSelection selection,
  ) {
    final request = buildRequest(snapshot, selection);
    final idempotencyKey = idempotencyKeyFactory().trim();
    if (idempotencyKey.isEmpty) {
      throw StateError('trip share idempotency key must not be blank');
    }
    return facet.createSnapshot(request, idempotencyKey: idempotencyKey);
  }

  CreateTripShareSnapshotRequest buildRequest(
    TripJourneySnapshot snapshot,
    TripShareSelection selection,
  ) {
    if (!snapshot.usesOneCurrentRevision) {
      throw StateError('trip projections do not use one current revision');
    }
    final sourceDigest = snapshot.timeline.sourceDigest.trim();
    if (sourceDigest.isEmpty) {
      throw StateError('trip timeline source digest must not be blank');
    }

    final availableMomentIds = snapshot.moments.moments
        .map((moment) => moment.momentId)
        .toSet();
    final selectedMomentIds = _momentIdsFor(snapshot, selection);
    if (!availableMomentIds.containsAll(selectedMomentIds)) {
      throw ArgumentError.value(
        selectedMomentIds,
        'selection.momentIds',
        'contains a moment outside the current trip snapshot',
      );
    }

    return CreateTripShareSnapshotRequest(
      tripId: snapshot.plan.tripId,
      sourceRevisionId: snapshot.timeline.currentRevisionId,
      sourceDigest: sourceDigest,
      scope: selection.scope,
      dayIndex: selection.dayIndex,
      itemId: selection.itemId,
      momentIds: selectedMomentIds,
      visibility: selection.visibility,
    );
  }

  List<String> _momentIdsFor(
    TripJourneySnapshot snapshot,
    TripShareSelection selection,
  ) {
    switch (selection.scope) {
      case TripShareSnapshotScope.full:
      case TripShareSnapshotScope.route:
        return List<String>.unmodifiable(snapshot.timeline.sourceMomentIds);
      case TripShareSnapshotScope.day:
        final dayIndex = selection.dayIndex;
        if (dayIndex == null ||
            !snapshot.timeline.days.any((day) => day.dayIndex == dayIndex)) {
          throw ArgumentError.value(dayIndex, 'selection.dayIndex');
        }
        return List<String>.unmodifiable(
          snapshot.moments.moments
              .where((moment) => moment.dayIndex == dayIndex)
              .map((moment) => moment.momentId),
        );
      case TripShareSnapshotScope.item:
        final itemId = selection.itemId?.trim() ?? '';
        final dayIndex = selection.dayIndex;
        final itemExists = snapshot.timeline.days.any(
          (day) =>
              day.dayIndex == dayIndex &&
              day.items.any((item) => item.itemId == itemId),
        );
        if (dayIndex == null || itemId.isEmpty || !itemExists) {
          throw ArgumentError.value(itemId, 'selection.itemId');
        }
        return List<String>.unmodifiable(
          snapshot.moments.moments
              .where((moment) => moment.itemId == itemId)
              .map((moment) => moment.momentId),
        );
      case TripShareSnapshotScope.momentCollection:
        final normalized = selection.momentIds
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toSet()
            .toList(growable: false);
        if (normalized.isEmpty) {
          throw ArgumentError.value(selection.momentIds, 'selection.momentIds');
        }
        return normalized;
    }
  }
}

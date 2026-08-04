import 'package:quwoquan_app/travel/travel/trip_plan_content_link/application/trip_content_link_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripContentTarget {
  const TripContentTarget.trip()
    : kind = TripPlanContentLinkTargetKind.trip,
      dayIndex = null,
      itemId = null;

  const TripContentTarget.day(this.dayIndex)
    : kind = TripPlanContentLinkTargetKind.day,
      itemId = null;

  const TripContentTarget.item({required this.dayIndex, required this.itemId})
    : kind = TripPlanContentLinkTargetKind.item;

  final TripPlanContentLinkTargetKind kind;
  final int? dayIndex;
  final String? itemId;
}

final class TripContentLinkPutIntent {
  const TripContentLinkPutIntent(this.request, this.idempotencyKey);

  final PutTripPlanContentLinkRequest request;
  final String idempotencyKey;
}

final class TripContentLinkRemovalIntent {
  const TripContentLinkRemovalIntent(this.request, this.idempotencyKey);

  final RemoveTripPlanContentLinkRequest request;
  final String idempotencyKey;
}

/// 只接受 Content owner Reader 提供的 postId/sourceVersion，不接受本地草稿
/// 或未经权限校验的缓存 Post。
final class TripContentLinkCoordinator {
  TripContentLinkCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripContentLinkFacet _facet;
  final String Function(String scope) _idempotencyKeyFactory;

  TripContentLinkPutIntent preparePut({
    required TripJourneySnapshot snapshot,
    required String postId,
    required int sourceVersion,
    required TripContentTarget target,
    required TripPlanContentLinkVisibility visibility,
    TripPlanContentLinkSlice? current,
    String? idempotencyKey,
  }) {
    if (!snapshot.usesOneCurrentRevision) {
      throw StateError('Trip projections must use one current revision');
    }
    final normalizedPostId = postId.trim();
    if (normalizedPostId.isEmpty || sourceVersion <= 0) {
      throw ArgumentError('Canonical Post identity and version are required');
    }
    _validateTarget(snapshot, target);
    if (current != null &&
        (current.tripId != snapshot.plan.tripId ||
            current.postId != normalizedPostId)) {
      throw ArgumentError('Current content link does not own the target');
    }
    return TripContentLinkPutIntent(
      PutTripPlanContentLinkRequest(
        tripId: snapshot.plan.tripId,
        postId: normalizedPostId,
        expectedVersion: current?.version ?? 0,
        revisionNumber: snapshot.plan.currentRevisionNumber,
        targetKind: target.kind,
        dayIndex: target.dayIndex,
        itemId: _nullableTrim(target.itemId),
        visibility: visibility,
        sourceVersion: sourceVersion,
      ),
      _nextKey('put', override: idempotencyKey),
    );
  }

  TripContentLinkRemovalIntent prepareRemoval({
    required TripPlanContentLinkSlice current,
    required String reason,
  }) {
    final normalizedReason = reason.trim();
    if (current.tripId.trim().isEmpty ||
        current.postId.trim().isEmpty ||
        current.version <= 0 ||
        current.status != TripPlanContentLinkStatus.active ||
        normalizedReason.isEmpty) {
      throw ArgumentError('Active content link and reason are required');
    }
    return TripContentLinkRemovalIntent(
      RemoveTripPlanContentLinkRequest(
        tripId: current.tripId,
        postId: current.postId,
        expectedVersion: current.version,
        reason: normalizedReason,
      ),
      _nextKey('remove'),
    );
  }

  Future<TripPlanContentLinkSlice> put(TripContentLinkPutIntent intent) =>
      _facet.put(intent.request, idempotencyKey: intent.idempotencyKey);

  Future<TripPlanContentLinkSlice> remove(
    TripContentLinkRemovalIntent intent,
  ) => _facet.remove(intent.request, idempotencyKey: intent.idempotencyKey);

  String _nextKey(String scope, {String? override}) {
    final key = (override ?? _idempotencyKeyFactory(scope)).trim();
    if (key.isEmpty) {
      throw StateError('Trip content link idempotency key must not be blank');
    }
    return key;
  }
}

void _validateTarget(TripJourneySnapshot snapshot, TripContentTarget target) {
  if (target.kind == TripPlanContentLinkTargetKind.trip) {
    if (target.dayIndex != null || _nullableTrim(target.itemId) != null) {
      throw ArgumentError.value(target, 'target');
    }
    return;
  }
  final dayIndex = target.dayIndex;
  if (dayIndex == null) {
    throw ArgumentError.value(target, 'target');
  }
  final day = snapshot.timeline.days
      .where((candidate) => candidate.dayIndex == dayIndex)
      .firstOrNull;
  if (day == null) {
    throw ArgumentError.value(dayIndex, 'target.dayIndex');
  }
  final itemId = _nullableTrim(target.itemId);
  if (target.kind == TripPlanContentLinkTargetKind.day && itemId != null ||
      target.kind == TripPlanContentLinkTargetKind.item &&
          (itemId == null || !day.items.any((item) => item.itemId == itemId))) {
    throw ArgumentError.value(itemId, 'target.itemId');
  }
}

String? _nullableTrim(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

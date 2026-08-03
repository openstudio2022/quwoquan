// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_facet.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_share_facet.dart';
import 'package:quwoquan_app/application/travel/trip_share_publication_continuation.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  final handler = TripSharePublicationContinuationHandler(
    shareFacet: const _UnusedShareFacet(),
    journeyLoader: TripJourneyLoader(const _UnusedJourneyQuery()),
    contentLinkCoordinator: TripContentLinkCoordinator(
      const _UnusedContentLinkFacet(),
      (_) => 'unused',
    ),
  );

  test('share scope maps to explicit trip day and item targets', () {
    final full = handler.targetFor(
      _snapshot(scope: TripShareSnapshotScope.full),
    );
    final day = handler.targetFor(
      _snapshot(scope: TripShareSnapshotScope.day, dayIndex: 2),
    );
    final item = handler.targetFor(
      _snapshot(
        scope: TripShareSnapshotScope.item,
        dayIndex: 2,
        itemId: 'item-2',
      ),
    );

    expect(full.kind, TripPlanContentLinkTargetKind.trip);
    expect(day.kind, TripPlanContentLinkTargetKind.day);
    expect(day.dayIndex, 2);
    expect(item.kind, TripPlanContentLinkTargetKind.item);
    expect(item.dayIndex, 2);
    expect(item.itemId, 'item-2');
  });

  test('moment collection chooses the narrowest truthful shared target', () {
    final item = handler.targetFor(
      _snapshot(
        scope: TripShareSnapshotScope.momentCollection,
        moments: const <TripShareMomentSlice>[
          TripShareMomentSlice(
            momentId: 'm1',
            dayIndex: 1,
            itemId: 'item-1',
            kind: 'image',
          ),
          TripShareMomentSlice(
            momentId: 'm2',
            dayIndex: 1,
            itemId: 'item-1',
            kind: 'text',
          ),
        ],
      ),
    );
    final day = handler.targetFor(
      _snapshot(
        scope: TripShareSnapshotScope.momentCollection,
        moments: const <TripShareMomentSlice>[
          TripShareMomentSlice(
            momentId: 'm1',
            dayIndex: 1,
            itemId: 'item-1',
            kind: 'image',
          ),
          TripShareMomentSlice(momentId: 'm2', dayIndex: 1, kind: 'text'),
        ],
      ),
    );
    final trip = handler.targetFor(
      _snapshot(
        scope: TripShareSnapshotScope.momentCollection,
        moments: const <TripShareMomentSlice>[
          TripShareMomentSlice(momentId: 'm1', dayIndex: 1, kind: 'image'),
          TripShareMomentSlice(momentId: 'm2', dayIndex: 2, kind: 'text'),
        ],
      ),
    );

    expect(item.kind, TripPlanContentLinkTargetKind.item);
    expect(day.kind, TripPlanContentLinkTargetKind.day);
    expect(trip.kind, TripPlanContentLinkTargetKind.trip);
  });
}

TripShareSnapshot _snapshot({
  required TripShareSnapshotScope scope,
  int? dayIndex,
  String? itemId,
  List<TripShareMomentSlice> moments = const <TripShareMomentSlice>[],
}) {
  return TripShareSnapshot(
    id: 'share-1',
    version: 1,
    tripId: 'trip-1',
    sourceRevisionId: 'revision-1',
    sourceRevisionNumber: 1,
    sourceDigest: 'sha256:source',
    scope: scope,
    dayIndex: dayIndex,
    itemId: itemId,
    momentIds: moments.map((moment) => moment.momentId).toList(),
    visibility: TripShareSnapshotVisibility.public,
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    items: const <TripShareItemSlice>[],
    moments: moments,
    contentLinks: const <TripShareContentLinkSlice>[],
    routeStops: const <TripShareRouteStopSlice>[],
    createdByPersonaId: 'persona-1',
    status: TripShareSnapshotStatus.active,
    createdAt: DateTime.utc(2026, 8, 2),
  );
}

final class _UnusedShareFacet implements TripShareFacet {
  const _UnusedShareFacet();

  @override
  Future<TripShareSnapshot> createSnapshot(
    CreateTripShareSnapshotRequest request, {
    required String idempotencyKey,
  }) => throw UnimplementedError();

  @override
  Future<TripShareSnapshot> getSnapshot(String snapshotId) =>
      throw UnimplementedError();
}

final class _UnusedJourneyQuery implements TripJourneyQuery {
  const _UnusedJourneyQuery();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

final class _UnusedContentLinkFacet implements TripContentLinkFacet {
  const _UnusedContentLinkFacet();

  @override
  Future<TripPlanContentLinkSlice> put(
    PutTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) => throw UnimplementedError();

  @override
  Future<TripPlanContentLinkSlice> remove(
    RemoveTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) => throw UnimplementedError();
}

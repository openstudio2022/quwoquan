import 'package:quwoquan_app/application/travel/trip_content_link_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_share_facet.dart';
import 'package:quwoquan_app/application/content/post/post_publication_continuation_registry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 把已发布游记回写到来源 Trip 的唯一 Content -> Travel continuation adapter。
///
/// 来源只接受冻结的 TripShareSnapshot 引用；不会回读编辑器 entityRefs、群消息或
/// 当前页面状态来猜行程目标。
final class TripSharePublicationContinuationHandler
    implements PostPublicationContinuationHandler {
  const TripSharePublicationContinuationHandler({
    required this.shareFacet,
    required this.journeyLoader,
    required this.contentLinkCoordinator,
  });

  final TripShareFacet shareFacet;
  final TripJourneyLoader journeyLoader;
  final TripContentLinkCoordinator contentLinkCoordinator;

  @override
  String get operationId =>
      AppCloudOperationIds.travelTripPlanContentLinkPutTripPlanContentLink;

  @override
  Future<void> apply({
    required CreateDraftPublicationContinuationRef continuation,
    required PostPublicationReceipt receipt,
  }) async {
    try {
      final source = _parseSource(continuation.sourceEntityRef);
      final snapshot = await shareFacet.getSnapshot(source.snapshotId);
      if (snapshot.id != source.snapshotId ||
          snapshot.version != source.version ||
          snapshot.status != TripShareSnapshotStatus.active) {
        throw const FormatException('snapshot_identity_mismatch');
      }
      final journey = await journeyLoader.load(snapshot.tripId);
      final target = targetFor(snapshot);
      final visibility = switch (snapshot.visibility) {
        TripShareSnapshotVisibility.public =>
          TripPlanContentLinkVisibility.public,
        TripShareSnapshotVisibility.tripMembers =>
          TripPlanContentLinkVisibility.tripMembers,
      };
      final intent = contentLinkCoordinator.preparePut(
        snapshot: journey,
        postId: receipt.postId,
        sourceVersion: receipt.committedVersion,
        target: target,
        visibility: visibility,
        idempotencyKey:
            'travel-content-link-publication:${receipt.localDraftId}:${receipt.postId}',
      );
      final linked = await contentLinkCoordinator.put(intent);
      if (linked.tripId != snapshot.tripId ||
          linked.postId != receipt.postId ||
          linked.sourceVersion != receipt.committedVersion ||
          linked.targetKind != target.kind ||
          linked.dayIndex != target.dayIndex ||
          linked.itemId != target.itemId ||
          linked.visibility != visibility ||
          linked.status != TripPlanContentLinkStatus.active) {
        throw const FormatException('content_link_receipt_mismatch');
      }
    } on PostPublicationContinuationRejectedException {
      rethrow;
    } on FormatException catch (error) {
      throw PostPublicationContinuationRejectedException(error.message);
    } on ArgumentError {
      throw const PostPublicationContinuationRejectedException(
        'invalid_trip_target',
      );
    } on StateError {
      throw const PostPublicationContinuationRejectedException(
        'stale_trip_projection',
      );
    }
  }

  TripContentTarget targetFor(TripShareSnapshot snapshot) {
    return switch (snapshot.scope) {
      TripShareSnapshotScope.full ||
      TripShareSnapshotScope.route => const TripContentTarget.trip(),
      TripShareSnapshotScope.day => TripContentTarget.day(
        _requiredDayIndex(snapshot.dayIndex),
      ),
      TripShareSnapshotScope.item => TripContentTarget.item(
        dayIndex: _requiredDayIndex(snapshot.dayIndex),
        itemId: _requiredItemId(snapshot.itemId),
      ),
      TripShareSnapshotScope.momentCollection => _momentCollectionTarget(
        snapshot,
      ),
    };
  }
}

final class _TripShareSnapshotSource {
  const _TripShareSnapshotSource(this.snapshotId, this.version);

  final String snapshotId;
  final int version;
}

_TripShareSnapshotSource _parseSource(String value) {
  const prefix = 'travel.TripShareSnapshot:';
  final normalized = value.trim();
  if (!normalized.startsWith(prefix)) {
    throw const FormatException('invalid_snapshot_reference');
  }
  final identity = normalized.substring(prefix.length);
  final separator = identity.lastIndexOf('@');
  final snapshotId = separator <= 0 ? '' : identity.substring(0, separator);
  final version = separator <= 0
      ? null
      : int.tryParse(identity.substring(separator + 1));
  if (snapshotId.trim().isEmpty || version == null || version <= 0) {
    throw const FormatException('invalid_snapshot_reference');
  }
  return _TripShareSnapshotSource(snapshotId.trim(), version);
}

TripContentTarget _momentCollectionTarget(TripShareSnapshot snapshot) {
  if (snapshot.moments.isEmpty) {
    throw const FormatException('empty_moment_collection');
  }
  final days = snapshot.moments.map((moment) => moment.dayIndex).toSet();
  final itemIds = snapshot.moments
      .map((moment) => moment.itemId?.trim() ?? '')
      .toSet();
  if (days.length == 1 && itemIds.length == 1 && itemIds.single.isNotEmpty) {
    return TripContentTarget.item(
      dayIndex: days.single,
      itemId: itemIds.single,
    );
  }
  if (days.length == 1) {
    return TripContentTarget.day(days.single);
  }
  return const TripContentTarget.trip();
}

int _requiredDayIndex(int? value) {
  if (value == null || value < 1) {
    throw const FormatException('missing_day_target');
  }
  return value;
}

String _requiredItemId(String? value) {
  final normalized = value?.trim() ?? '';
  if (normalized.isEmpty) {
    throw const FormatException('missing_item_target');
  }
  return normalized;
}

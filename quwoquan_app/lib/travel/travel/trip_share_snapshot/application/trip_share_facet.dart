import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 隐私裁剪旅行快照的唯一 App 读写面。
abstract interface class TripShareFacet {
  Future<TripShareSnapshot> getSnapshot(String snapshotId);

  Future<TripShareSnapshot> createSnapshot(
    CreateTripShareSnapshotRequest request, {
    required String idempotencyKey,
  });
}

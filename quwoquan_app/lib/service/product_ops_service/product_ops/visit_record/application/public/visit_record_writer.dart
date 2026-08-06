import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';

/// VisitRecord 的公开写入边界。
abstract interface class VisitRecordWriter {
  Future<RecordVisitReceipt> recordVisit(
    RecordVisitRequest request, {
    required String idempotencyKey,
  });
}

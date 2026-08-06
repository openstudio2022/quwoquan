import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/application/public/visit_record_writer.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef OpsVisitInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required String idempotencyKey,
    });

/// VisitRecord 对象的 canonical typed append 写面。
/// App consumer 唯一能力为 record_visit。
/// 访问统计读面（GetVisitStats）是 operator 能力，App 端不消费。
class RemoteOpsVisitAppendWriter implements VisitRecordWriter {
  const RemoteOpsVisitAppendWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final OpsVisitInvocationContextFactory invocationContext;

  @override
  Future<RecordVisitReceipt> recordVisit(
    RecordVisitRequest request, {
    required String idempotencyKey,
  }) {
    final key = idempotencyKey.trim();
    if (key.isEmpty) {
      throw ArgumentError.value(
        idempotencyKey,
        'idempotencyKey',
        'must not be empty',
      );
    }
    return client.opsVisitRecordRecordVisit(
      request,
      context: invocationContext(
        OpsRequestPageIds.recordVisit,
        idempotencyKey: key,
      ),
    );
  }
}

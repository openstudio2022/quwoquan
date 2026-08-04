import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef OpsEventRecordInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required String idempotencyKey,
    });

/// EventRecord 对象的唯一 App 出站写面。
///
/// 调用方只能提交 canonical generated request；HTTP path、header、response
/// decoder、重试与鉴权均由 [GeneratedCloudOperationClient] 负责。
abstract interface class OpsEventRecordBatchWriter {
  Future<ops.EventRecordBatchReceipt> reportEventBatch(
    ops.EventRecordBatchRequest request, {
    required String idempotencyKey,
  });

  Future<ops.EventRecordBatchReceipt> reportRuntimeLogBatch(
    ops.RuntimeLogBatchRequest request, {
    required String idempotencyKey,
  });
}

final class RemoteOpsEventRecordBatchWriter
    implements OpsEventRecordBatchWriter {
  const RemoteOpsEventRecordBatchWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final OpsEventRecordInvocationContextFactory invocationContext;

  @override
  Future<ops.EventRecordBatchReceipt> reportEventBatch(
    ops.EventRecordBatchRequest request, {
    required String idempotencyKey,
  }) => client.opsEventRecordReportEventBatch(
    request,
    context: invocationContext(
      OpsRequestPageIds.reportEventBatch,
      idempotencyKey: idempotencyKey,
    ),
  );

  @override
  Future<ops.EventRecordBatchReceipt> reportRuntimeLogBatch(
    ops.RuntimeLogBatchRequest request, {
    required String idempotencyKey,
  }) => client.opsEventRecordReportRuntimeLogBatch(
    request,
    context: invocationContext(
      OpsRequestPageIds.reportRuntimeLogBatch,
      idempotencyKey: idempotencyKey,
    ),
  );
}

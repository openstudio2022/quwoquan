import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef RtcCallInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

CloudOperationInvocationContext rtcInvocationWithIdempotencyKey(
  CloudOperationInvocationContext base,
  String idempotencyKey,
) => CloudOperationInvocationContext(
  surfaceId: base.surfaceId,
  clientPageId: base.clientPageId,
  actor: base.actor,
  routeId: base.routeId,
  referralSource: base.referralSource,
  feedRequestId: base.feedRequestId,
  shareId: base.shareId,
  modelId: base.modelId,
  experimentBucket: base.experimentBucket,
  idempotencyKey: idempotencyKey,
  deadlineAt: base.deadlineAt,
  cancellation: base.cancellation,
);

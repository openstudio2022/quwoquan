enum IncomingCallPresentationSource {
  realtime('realtime'),
  nativePush('native_push');

  const IncomingCallPresentationSource(this.wireName);

  final String wireName;
}

final class IncomingCallPresentationReceipt {
  const IncomingCallPresentationReceipt({
    required this.callId,
    required this.deliveryKey,
    required this.source,
    required this.presentedAt,
  });

  final String callId;
  final String deliveryKey;
  final IncomingCallPresentationSource source;
  final DateTime presentedAt;
}

/// NotificationDeliveryJob（process_manager）的端侧写端口：来电展示成功后回执，
/// 推进这一次投递任务的流程状态。
///
/// 命名遵循 `APP_PROCESS_PORT_NAMING` 的 `*ProcessCommandWriter`，与聚合的
/// `*CommandWriter` 在类型上不可混用。Remote adapter 只调用 generated operation
/// client；本接口不接收 path / operationId。
abstract interface class NotificationDeliveryJobProcessCommandWriter {
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt);
}

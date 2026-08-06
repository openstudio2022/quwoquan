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

/// 来电展示成功后的 typed ACK 注入点。
///
/// Remote adapter 只调用 generated operation client；本接口不接收 path / operationId。
abstract interface class IncomingCallPresentationAcknowledger {
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt);
}

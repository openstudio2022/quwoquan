// Published Content post follow-up orchestration contract.
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class CreateDraftPublicationContinuationRef {
  const CreateDraftPublicationContinuationRef({
    required this.operationId,
    required this.sourceEntityRef,
  });

  final String operationId;
  final String sourceEntityRef;

  factory CreateDraftPublicationContinuationRef.fromStorageMap(
    Map<String, dynamic> map,
  ) {
    final operationId = (map['operationId'] ?? '').toString().trim();
    final sourceEntityRef = (map['sourceEntityRef'] ?? '').toString().trim();
    if (operationId.isEmpty || sourceEntityRef.isEmpty) {
      throw const FormatException('invalid publication continuation');
    }
    return CreateDraftPublicationContinuationRef(
      operationId: operationId,
      sourceEntityRef: sourceEntityRef,
    );
  }

  Map<String, dynamic> toStorageMap() => <String, dynamic>{
    'operationId': operationId,
    'sourceEntityRef': sourceEntityRef,
  };
}

final class PostPublicationContinuationRejectedException implements Exception {
  const PostPublicationContinuationRejectedException(this.reason);

  final String reason;

  static const String errorCode = 'publication_continuation_rejected';
}

abstract interface class PostPublicationContinuationHandler {
  String get operationId;

  Future<void> apply({
    required CreateDraftPublicationContinuationRef continuation,
    required PostPublicationReceipt receipt,
  });
}

/// Content 发布队列只识别 canonical operationId，不依赖 Travel 或其它领域。
///
/// 新增发布后动作时通过对象所属领域注册 handler；未知或重复 operation 必须
/// fail closed，避免已发布 Post 被静默挂到错误业务对象。
final class PostPublicationContinuationRegistry {
  PostPublicationContinuationRegistry(
    Iterable<PostPublicationContinuationHandler> handlers,
  ) : _handlers = _indexHandlers(handlers);

  final Map<String, PostPublicationContinuationHandler> _handlers;

  Future<void> apply({
    required CreateDraftPublicationContinuationRef continuation,
    required PostPublicationReceipt receipt,
  }) async {
    final operationId = continuation.operationId.trim();
    final handler = _handlers[operationId];
    if (handler == null) {
      throw const PostPublicationContinuationRejectedException(
        'unsupported_operation',
      );
    }
    await handler.apply(continuation: continuation, receipt: receipt);
  }
}

Map<String, PostPublicationContinuationHandler> _indexHandlers(
  Iterable<PostPublicationContinuationHandler> handlers,
) {
  final indexed = <String, PostPublicationContinuationHandler>{};
  for (final handler in handlers) {
    final operationId = handler.operationId.trim();
    if (operationId.isEmpty || indexed.containsKey(operationId)) {
      throw StateError('Publication continuation operation must be unique');
    }
    indexed[operationId] = handler;
  }
  return Map<String, PostPublicationContinuationHandler>.unmodifiable(indexed);
}

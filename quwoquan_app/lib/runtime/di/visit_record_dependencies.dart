import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/application/public/visit_record_writer.dart';
import 'package:quwoquan_app/runtime/observability/visit/visit_append_port.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';

/// runtime VisitAppendPort 到 VisitRecord 对象写面的唯一 anti-corruption bridge。
final class VisitRecordAppendBridge implements VisitAppendPort {
  const VisitRecordAppendBridge(this.writer);

  final VisitRecordWriter writer;

  @override
  Future<void> recordVisit(VisitAppendInput input) async {
    final idempotencyKey = input.idempotencyKey.trim();
    if (idempotencyKey.isEmpty) {
      throw ArgumentError.value(
        input.idempotencyKey,
        'idempotencyKey',
        'must not be empty',
      );
    }
    await writer.recordVisit(
      RecordVisitRequest(
        targetType: _visitTargetType(input.targetType),
        targetKey: input.targetKey,
      ),
      idempotencyKey: idempotencyKey,
    );
  }
}

VisitTargetType _visitTargetType(String value) {
  return switch (value.trim()) {
    'page' => VisitTargetType.page,
    'post' => VisitTargetType.post,
    'circle' => VisitTargetType.circle,
    'user' => VisitTargetType.user,
    _ => throw ArgumentError.value(
      value,
      'targetType',
      'must be page, post, circle, or user',
    ),
  };
}

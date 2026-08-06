/// 壳层访问记录向 Product Ops 提交的最小稳定输入。
///
/// 这是 runtime 拥有的 Port；具体 Cloud operation、page id 与 wire enum 只存在于
/// ops Adapter，避免本地访问缓存反向依赖业务域实现。
final class VisitAppendInput {
  const VisitAppendInput({
    required this.idempotencyKey,
    required this.targetType,
    required this.targetKey,
  });

  final String idempotencyKey;
  final String targetType;
  final String targetKey;

  factory VisitAppendInput.fromStorageJson(Map<String, dynamic> json) {
    const allowedFields = <String>{'idempotencyKey', 'targetType', 'targetKey'};
    final unknownFields = json.keys.toSet().difference(allowedFields);
    if (unknownFields.isNotEmpty) {
      throw FormatException(
        'visit storage record contains unknown fields: '
        '${unknownFields.toList()..sort()}',
      );
    }
    return VisitAppendInput(
      idempotencyKey: _requiredStorageString(json, 'idempotencyKey'),
      targetType: _requiredStorageString(json, 'targetType'),
      targetKey: _requiredStorageString(json, 'targetKey'),
    );
  }

  Map<String, dynamic> toStorageJson() => <String, dynamic>{
    'idempotencyKey': idempotencyKey,
    'targetType': targetType,
    'targetKey': targetKey,
  };
}

String _requiredStorageString(Map<String, dynamic> json, String field) {
  final value = json[field];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('visit storage record requires $field');
  }
  return value.trim();
}

abstract interface class VisitAppendPort {
  Future<void> recordVisit(VisitAppendInput input);
}

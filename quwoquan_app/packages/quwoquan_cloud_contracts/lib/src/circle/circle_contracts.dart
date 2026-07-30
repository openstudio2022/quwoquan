import '../operation_request_payload.dart';
part '../generated/requests/circle/circle_contracts.requests.g.dart';

/// Circle 聚合生命周期与配置命令的 pure contracts。
/// 真相源：quwoquan_service/services/circle-service/contracts/circle_management/circle/{service,fields}.yaml。
/// 命名状态迁移由服务端内部 version CAS 保护，命令不携带调用方版本字段。

enum CircleLifecycleStatus { active, archived, deleted }

final class CircleSectionConfigInput {
  CircleSectionConfigInput({
    required String sectionType,
    required this.visible,
    required this.order,
    this.customTitle,
  }) : sectionType = _required(sectionType, 'sectionType') {
    if (order < 0) {
      throw ArgumentError.value(order, 'order', 'must be >= 0');
    }
  }

  final String sectionType;
  final bool visible;
  final int order;
  final String? customTitle;
}

final class CircleCommandResult {
  const CircleCommandResult({
    required this.circleId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String circleId;
  final int version;
  final CircleLifecycleStatus status;
  final bool idempotentReplay;
}

abstract interface class CircleLifecycleCommandWriter {
  Future<CircleCommandResult> createCircle(CreateCircleCommand command);

  Future<CircleCommandResult> updateCircle(UpdateCircleCommand command);

  Future<CircleCommandResult> archiveCircle(ArchiveCircleCommand command);
}

abstract interface class CircleConfigurationCommandWriter {
  Future<CircleCommandResult> updateCircleSections(
    UpdateCircleSectionsCommand command,
  );
}

CircleCommandResult decodeCircleCommandResult(Object? value) {
  final map = _object(value, 'CircleCommandResult');
  _only(map, const <String>{
    'circleId',
    'version',
    'status',
    'idempotentReplay',
  });
  return CircleCommandResult(
    circleId: _string(map, 'circleId'),
    version: _positiveInt(map, 'version'),
    status: _circleLifecycleStatus(map['status']),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

CircleLifecycleStatus _circleLifecycleStatus(Object? value) {
  return switch (value) {
    'active' => CircleLifecycleStatus.active,
    'archived' => CircleLifecycleStatus.archived,
    'deleted' => CircleLifecycleStatus.deleted,
    _ => throw FormatException('unknown circle status: $value'),
  };
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('unexpected key: $key');
    }
  }
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0) {
    throw FormatException('$key must be a positive integer');
  }
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('$key must be a boolean');
  }
  return value;
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

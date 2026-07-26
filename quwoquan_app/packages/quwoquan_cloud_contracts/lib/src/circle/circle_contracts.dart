import '../operation_request_payload.dart';

/// Circle 聚合生命周期与配置命令的 pure contracts。
/// 真相源：quwoquan_service/services/circle-service/contracts/circle_management/circle/{service,fields}.yaml。
/// 命名状态迁移由服务端内部 version CAS 保护，命令不携带调用方版本字段。

enum CircleLifecycleStatus { active, archived, deleted }

final class CreateCircleCommand {
  CreateCircleCommand({
    required String name,
    this.description,
    this.rulesText,
    this.welcomeMessage,
    this.coverUrl,
    this.iconUrl,
    this.category,
    this.subCategory,
    List<String> tags = const <String>[],
    this.visibility,
    this.joinPolicy,
    this.kind,
    this.displaySubjectType,
    this.followEnabled,
    this.autoSyncChat,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
  }) : name = _required(name, 'name'),
       tags = List<String>.unmodifiable(
         tags.map((tag) => tag.trim()).where((tag) => tag.isNotEmpty),
       ) {
    _validateGovernanceText(rulesText, welcomeMessage);
  }

  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String> tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;
}

/// PATCH 语义：仅编码非 null 字段；空字符串表示清空该字段。
final class UpdateCircleCommand {
  UpdateCircleCommand({
    required String circleId,
    this.name,
    this.description,
    this.rulesText,
    this.welcomeMessage,
    this.coverUrl,
    this.iconUrl,
    this.category,
    this.subCategory,
    this.tags,
    this.visibility,
    this.joinPolicy,
    this.kind,
    this.displaySubjectType,
    this.followEnabled,
    this.autoSyncChat,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
  }) : circleId = _required(circleId, 'circleId') {
    if (name != null && name!.trim().isEmpty) {
      throw ArgumentError.value(name, 'name', 'must not be blank when set');
    }
    _validateGovernanceText(rulesText, welcomeMessage);
  }

  final String circleId;
  final String? name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;
}

final class ArchiveCircleCommand {
  ArchiveCircleCommand({required String circleId})
    : circleId = _required(circleId, 'circleId');

  final String circleId;
}

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

final class UpdateCircleSectionsCommand {
  UpdateCircleSectionsCommand({
    required String circleId,
    required List<CircleSectionConfigInput> sections,
  }) : circleId = _required(circleId, 'circleId'),
       sections = List<CircleSectionConfigInput>.unmodifiable(sections) {
    if (sections.isEmpty || sections.length > 16) {
      throw ArgumentError.value(
        sections.length,
        'sections',
        'must contain 1..16 entries',
      );
    }
  }

  final String circleId;
  final List<CircleSectionConfigInput> sections;
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

CloudOperationRequestPayload encodeCreateCircleCommand(
  CreateCircleCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'name': command.name,
    if (command.description != null) 'description': command.description,
    if (command.rulesText != null) 'rulesText': command.rulesText,
    if (command.welcomeMessage != null)
      'welcomeMessage': command.welcomeMessage,
    if (command.coverUrl != null) 'coverUrl': command.coverUrl,
    if (command.iconUrl != null) 'iconUrl': command.iconUrl,
    if (command.category != null) 'category': command.category,
    if (command.subCategory != null) 'subCategory': command.subCategory,
    if (command.tags.isNotEmpty) 'tags': command.tags,
    if (command.visibility != null) 'visibility': command.visibility,
    if (command.joinPolicy != null) 'joinPolicy': command.joinPolicy,
    if (command.kind != null) 'kind': command.kind,
    if (command.displaySubjectType != null)
      'displaySubjectType': command.displaySubjectType,
    if (command.followEnabled != null) 'followEnabled': command.followEnabled,
    if (command.autoSyncChat != null) 'autoSyncChat': command.autoSyncChat,
    if (command.linkedHomepageId != null)
      'linkedHomepageId': command.linkedHomepageId,
    if (command.linkedHomepageType != null)
      'linkedHomepageType': command.linkedHomepageType,
    if (command.linkedHomepageTitle != null)
      'linkedHomepageTitle': command.linkedHomepageTitle,
  },
);

CloudOperationRequestPayload encodeUpdateCircleCommand(
  UpdateCircleCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  body: <String, Object?>{
    if (command.name != null) 'name': command.name,
    if (command.description != null) 'description': command.description,
    if (command.rulesText != null) 'rulesText': command.rulesText,
    if (command.welcomeMessage != null)
      'welcomeMessage': command.welcomeMessage,
    if (command.coverUrl != null) 'coverUrl': command.coverUrl,
    if (command.iconUrl != null) 'iconUrl': command.iconUrl,
    if (command.category != null) 'category': command.category,
    if (command.subCategory != null) 'subCategory': command.subCategory,
    if (command.tags != null) 'tags': command.tags,
    if (command.visibility != null) 'visibility': command.visibility,
    if (command.joinPolicy != null) 'joinPolicy': command.joinPolicy,
    if (command.kind != null) 'kind': command.kind,
    if (command.displaySubjectType != null)
      'displaySubjectType': command.displaySubjectType,
    if (command.followEnabled != null) 'followEnabled': command.followEnabled,
    if (command.autoSyncChat != null) 'autoSyncChat': command.autoSyncChat,
    if (command.linkedHomepageId != null)
      'linkedHomepageId': command.linkedHomepageId,
    if (command.linkedHomepageType != null)
      'linkedHomepageType': command.linkedHomepageType,
    if (command.linkedHomepageTitle != null)
      'linkedHomepageTitle': command.linkedHomepageTitle,
  },
);

CloudOperationRequestPayload encodeArchiveCircleCommand(
  ArchiveCircleCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
);

CloudOperationRequestPayload encodeUpdateCircleSectionsCommand(
  UpdateCircleSectionsCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  body: <String, Object?>{
    'sections': command.sections
        .map(
          (section) => <String, Object?>{
            'sectionType': section.sectionType,
            'visible': section.visible,
            'order': section.order,
            if (section.customTitle != null)
              'customTitle': section.customTitle,
          },
        )
        .toList(growable: false),
  },
);

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

void _validateGovernanceText(String? rulesText, String? welcomeMessage) {
  if (rulesText != null && rulesText.runes.length > 2000) {
    throw ArgumentError.value(rulesText, 'rulesText', 'must not exceed 2000 runes');
  }
  if (welcomeMessage != null && welcomeMessage.runes.length > 500) {
    throw ArgumentError.value(
      welcomeMessage,
      'welcomeMessage',
      'must not exceed 500 runes',
    );
  }
}

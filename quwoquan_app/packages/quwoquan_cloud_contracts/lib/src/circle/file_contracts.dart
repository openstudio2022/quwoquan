import '../operation_request_payload.dart';

enum CircleFileType { file, folder }

enum CircleFileStatus { active, deleted }

final class CreateCircleFileCommand {
  CreateCircleFileCommand({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    required String name,
    required this.fileType,
    String? assetId,
  }) : circleId = _required(circleId, 'circleId'),
       name = _required(name, 'name'),
       groupId = _optional(groupId),
       parentFolderId = _optional(parentFolderId),
       assetId = _optional(assetId) {
    if (this.name.runes.length > 255) {
      throw ArgumentError.value(name, 'name', 'must contain at most 255 runes');
    }
    if (fileType == CircleFileType.file && this.assetId == null) {
      throw ArgumentError('CircleFile file requires a ready MediaAsset id');
    }
    if (fileType == CircleFileType.folder && this.assetId != null) {
      throw ArgumentError('CircleFile folder cannot bind a MediaAsset');
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String name;
  final CircleFileType fileType;
  final String? assetId;
}

final class UpdateCircleFileCommand {
  UpdateCircleFileCommand({
    required String circleId,
    required String fileId,
    required this.expectedVersion,
    this.parentFolderId,
    this.name,
  }) : circleId = _required(circleId, 'circleId'),
       fileId = _required(fileId, 'fileId') {
    _positive(expectedVersion, 'expectedVersion');
    if (name != null && (name!.trim().isEmpty || name!.runes.length > 255)) {
      throw ArgumentError.value(name, 'name', 'must contain 1..255 runes');
    }
    if (parentFolderId == null && name == null) {
      throw ArgumentError('CircleFile update must contain a field');
    }
  }

  final String circleId;
  final String fileId;
  final int expectedVersion;

  /// Empty string moves the object to the root; null omits the field.
  final String? parentFolderId;
  final String? name;
}

final class DeleteCircleFileCommand {
  DeleteCircleFileCommand({
    required String circleId,
    required String fileId,
    required this.expectedVersion,
  }) : circleId = _required(circleId, 'circleId'),
       fileId = _required(fileId, 'fileId') {
    _positive(expectedVersion, 'expectedVersion');
  }

  final String circleId;
  final String fileId;
  final int expectedVersion;
}

final class CircleFileQuery {
  CircleFileQuery({required String circleId, required String fileId})
    : circleId = _required(circleId, 'circleId'),
      fileId = _required(fileId, 'fileId');

  final String circleId;
  final String fileId;
}

final class CircleFileListQuery {
  CircleFileListQuery({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    String? cursor,
    this.limit = 20,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _optional(groupId),
       parentFolderId = _optional(parentFolderId),
       cursor = _optional(cursor) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be in 1..100');
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String? cursor;
  final int limit;
}

final class CircleFileCommandResult {
  const CircleFileCommandResult({
    required this.fileId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String fileId;
  final int version;
  final CircleFileStatus status;
  final bool idempotentReplay;
}

final class CircleFileSlice {
  const CircleFileSlice({
    required this.fileId,
    required this.version,
    required this.circleId,
    required this.groupId,
    required this.parentFolderId,
    required this.name,
    required this.fileType,
    required this.assetId,
    required this.mimeType,
    required this.sizeBytes,
    required this.uploaderPersonaId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String fileId;
  final int version;
  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String name;
  final CircleFileType fileType;
  final String? assetId;
  final String? mimeType;
  final int sizeBytes;
  final String uploaderPersonaId;
  final CircleFileStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class CircleFilePageSlice {
  const CircleFilePageSlice({required this.items, this.nextCursor});

  final List<CircleFileSlice> items;
  final String? nextCursor;
}

abstract interface class CircleFileCommandWriter {
  Future<CircleFileCommandResult> create(CreateCircleFileCommand command);
  Future<CircleFileCommandResult> update(UpdateCircleFileCommand command);
  Future<CircleFileCommandResult> delete(DeleteCircleFileCommand command);
}

abstract interface class CircleFileQueryReader {
  Future<CircleFileSlice> get(CircleFileQuery query);
  Future<CircleFilePageSlice> list(CircleFileListQuery query);
}

CloudOperationRequestPayload encodeCreateCircleFileCommand(
  CreateCircleFileCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  body: <String, Object?>{
    if (command.groupId != null) 'groupId': command.groupId,
    if (command.parentFolderId != null)
      'parentFolderId': command.parentFolderId,
    'name': command.name,
    'fileType': command.fileType.name,
    if (command.assetId != null) 'assetId': command.assetId,
  },
);

CloudOperationRequestPayload encodeUpdateCircleFileCommand(
  UpdateCircleFileCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'fileId': command.fileId,
  },
  headers: <String, String>{'If-Match': '"${command.expectedVersion}"'},
  body: <String, Object?>{
    if (command.parentFolderId != null)
      'parentFolderId': command.parentFolderId,
    if (command.name != null) 'name': command.name,
  },
);

CloudOperationRequestPayload encodeDeleteCircleFileCommand(
  DeleteCircleFileCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'fileId': command.fileId,
  },
  headers: <String, String>{'If-Match': '"${command.expectedVersion}"'},
);

CloudOperationRequestPayload encodeCircleFileQuery(CircleFileQuery query) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{
        'circleId': query.circleId,
        'fileId': query.fileId,
      },
    );

CloudOperationRequestPayload encodeCircleFileListQuery(
  CircleFileListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': query.circleId},
  queryParameters: <String, String>{
    if (query.groupId != null) 'groupId': query.groupId!,
    if (query.parentFolderId != null) 'parentFolderId': query.parentFolderId!,
    if (query.cursor != null) 'cursor': query.cursor!,
    'limit': query.limit.toString(),
  },
);

CircleFileCommandResult decodeCircleFileCommandResult(Object? value) {
  final map = _object(value, 'CircleFileCommandResult');
  _only(map, const <String>{'fileId', 'version', 'status', 'idempotentReplay'});
  return CircleFileCommandResult(
    fileId: _string(map, 'fileId'),
    version: _positiveInt(map, 'version'),
    status: _status(map['status']),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

CircleFileSlice decodeCircleFileSlice(Object? value) => _slice(value);

CircleFilePageSlice decodeCircleFilePageSlice(Object? value) {
  final map = _object(value, 'CircleFilePageSlice');
  _only(map, const <String>{'items', 'cursor'});
  final items = map['items'];
  if (items is! List<Object?>) {
    throw const FormatException('CircleFilePageSlice.items must be a list');
  }
  return CircleFilePageSlice(
    items: items.map(_slice).toList(growable: false),
    nextCursor: _optionalValue(map['cursor']),
  );
}

CircleFileSlice _slice(Object? value) {
  final map = _object(value, 'CircleFileSlice');
  _only(map, const <String>{
    'fileId',
    'version',
    'circleId',
    'groupId',
    'parentFolderId',
    'name',
    'fileType',
    'assetId',
    'mimeType',
    'sizeBytes',
    'uploaderPersonaId',
    'status',
    'createdAt',
    'updatedAt',
  });
  return CircleFileSlice(
    fileId: _string(map, 'fileId'),
    version: _positiveInt(map, 'version'),
    circleId: _string(map, 'circleId'),
    groupId: _optionalValue(map['groupId']),
    parentFolderId: _optionalValue(map['parentFolderId']),
    name: _string(map, 'name'),
    fileType: _fileType(map['fileType']),
    assetId: _optionalValue(map['assetId']),
    mimeType: _optionalValue(map['mimeType']),
    sizeBytes: _nonNegativeInt(map, 'sizeBytes'),
    uploaderPersonaId: _string(map, 'uploaderPersonaId'),
    status: _status(map['status']),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

CircleFileType _fileType(Object? value) => switch (value) {
  'file' => CircleFileType.file,
  'folder' => CircleFileType.folder,
  _ => throw FormatException('invalid CircleFileType: $value'),
};

CircleFileStatus _status(Object? value) => switch (value) {
  'active' => CircleFileStatus.active,
  'deleted' => CircleFileStatus.deleted,
  _ => throw FormatException('invalid CircleFileStatus: $value'),
};

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) throw FormatException('$label must be an object');
  return value.map((key, value) {
    if (key is! String) throw FormatException('$label key must be string');
    return MapEntry(key, value);
  });
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  final unknown = map.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) throw FormatException('unknown fields: $unknown');
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value;
}

String? _optionalValue(Object? value) {
  if (value == null || value == '') return null;
  if (value is! String) throw const FormatException('optional string invalid');
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be bool');
  return value;
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0) {
    throw FormatException('$key must be positive');
  }
  return value;
}

int _nonNegativeInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value < 0) {
    throw FormatException('$key must be non-negative');
  }
  return value;
}

DateTime _date(Map<String, Object?> map, String key) {
  final value = DateTime.tryParse(_string(map, key));
  if (value == null) throw FormatException('$key must be RFC3339');
  return value.toUtc();
}

void _positive(int value, String name) {
  if (value <= 0) throw ArgumentError.value(value, name, 'must be positive');
}

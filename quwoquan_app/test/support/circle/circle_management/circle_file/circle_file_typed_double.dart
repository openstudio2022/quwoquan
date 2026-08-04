import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha runner-only CircleFile fixture. It stores typed object state and
/// references MediaAsset IDs; it never models upload URLs or object keys.
final class AlphaCircleFileFacet
    implements CircleFileCommandWriter, CircleFileQueryReader {
  final Map<String, CircleFileSlice> _files = <String, CircleFileSlice>{};
  int _sequence = 0;

  @override
  Future<CircleFileCommandResult> create(
    CreateCircleFileCommand command,
  ) async {
    final fileId = 'alpha_circle_file_${++_sequence}';
    final file = CircleFileSlice(
      fileId: fileId,
      version: 1,
      circleId: command.circleId,
      groupId: command.groupId,
      parentFolderId: command.parentFolderId,
      name: command.name,
      fileType: command.fileType,
      assetId: command.assetId,
      mimeType: command.fileType == CircleFileType.file
          ? 'application/octet-stream'
          : null,
      sizeBytes: command.fileType == CircleFileType.file ? 1 : 0,
      uploaderPersonaId: _personaId,
      status: CircleFileStatus.active,
      createdAt: _now,
      updatedAt: _now,
    );
    _files[_key(command.circleId, fileId)] = file;
    return _result(file);
  }

  @override
  Future<CircleFileCommandResult> update(
    UpdateCircleFileCommand command,
  ) async {
    final key = _key(command.circleId, command.fileId);
    final current = _required(key, command.expectedVersion);
    final updated = CircleFileSlice(
      fileId: current.fileId,
      version: current.version + 1,
      circleId: current.circleId,
      groupId: current.groupId,
      parentFolderId: command.parentFolderId == null
          ? current.parentFolderId
          : command.parentFolderId!.isEmpty
          ? null
          : command.parentFolderId,
      name: command.name ?? current.name,
      fileType: current.fileType,
      assetId: current.assetId,
      mimeType: current.mimeType,
      sizeBytes: current.sizeBytes,
      uploaderPersonaId: current.uploaderPersonaId,
      status: current.status,
      createdAt: current.createdAt,
      updatedAt: _now,
    );
    _files[key] = updated;
    return _result(updated);
  }

  @override
  Future<CircleFileCommandResult> delete(
    DeleteCircleFileCommand command,
  ) async {
    final key = _key(command.circleId, command.fileId);
    final current = _required(key);
    if (current.status == CircleFileStatus.deleted) {
      return _result(current);
    }
    final deleted = CircleFileSlice(
      fileId: current.fileId,
      version: current.version + 1,
      circleId: current.circleId,
      groupId: current.groupId,
      parentFolderId: current.parentFolderId,
      name: current.name,
      fileType: current.fileType,
      assetId: current.assetId,
      mimeType: current.mimeType,
      sizeBytes: current.sizeBytes,
      uploaderPersonaId: current.uploaderPersonaId,
      status: CircleFileStatus.deleted,
      createdAt: current.createdAt,
      updatedAt: _now,
    );
    _files[key] = deleted;
    return _result(deleted);
  }

  @override
  Future<CircleFileSlice> get(CircleFileQuery query) async =>
      _required(_key(query.circleId, query.fileId));

  @override
  Future<CircleFilePageSlice> list(CircleFileListQuery query) async {
    final items = _files.values
        .where((file) => file.circleId == query.circleId)
        .where((file) => file.status == CircleFileStatus.active)
        .where((file) => file.groupId == query.groupId)
        .where((file) => file.parentFolderId == query.parentFolderId)
        .take(query.limit)
        .toList(growable: false);
    return CircleFilePageSlice(items: items);
  }

  CircleFileSlice _required(String key, [int? expectedVersion]) {
    final file = _files[key];
    if (file == null) throw StateError('alpha CircleFile not found');
    if (expectedVersion != null && file.version != expectedVersion) {
      throw StateError('alpha CircleFile version conflict');
    }
    return file;
  }

  CircleFileCommandResult _result(CircleFileSlice file) =>
      CircleFileCommandResult(
        fileId: file.fileId,
        version: file.version,
        status: file.status,
        idempotentReplay: false,
      );

  String _key(String circleId, String fileId) => '$circleId::$fileId';
  static const String _personaId = 'alpha_persona';
  DateTime get _now => DateTime.utc(2026, 7, 14);
}

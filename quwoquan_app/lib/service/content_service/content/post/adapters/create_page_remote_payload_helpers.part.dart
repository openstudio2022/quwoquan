part of 'create_page_remote_helpers.dart';

String _postPublicationIntentIdForLocalDraft(String localDraftId) {
  final canonicalDraftId = localDraftId.trim();
  if (canonicalDraftId.isEmpty) {
    throw ArgumentError.value(
      localDraftId,
      'localDraftId',
      'must not be blank',
    );
  }
  return 'post-publication:$canonicalDraftId';
}

List<PostSemanticMention> _postSemanticMentionsFromPayload(Object? raw) {
  if (raw == null) return const <PostSemanticMention>[];
  if (raw is! Iterable) {
    throw const FormatException('semanticMentions must be a list');
  }
  return List<PostSemanticMention>.unmodifiable(
    raw.indexed.map((entry) {
      final value = entry.$2;
      if (value is PostSemanticMention) return value;
      final path = 'semanticMentions[${entry.$1}]';
      return PostSemanticMention.fromWire(
        _requiredWireObject(value, path),
        path,
      );
    }),
  );
}

T? _optionalGeneratedWireValue<T>(
  Object? raw,
  String path,
  T Function(Map<String, Object?> map, String path) fromWire,
) {
  if (raw == null) return null;
  if (raw is T) return raw as T;
  return fromWire(_requiredWireObject(raw, path), path);
}

Map<String, Object?> _requiredWireObject(Object? raw, String path) {
  if (raw is! Map) {
    throw FormatException('$path must be an object');
  }
  return Map<String, Object?>.from(raw);
}

// ─── 创作页埋点 extras（避免在 UI 散写 Map 字面量）────────────────────────────

Map<String, Object?> createEditorSurfaceExtrasEditorKind(
  CreateEditorKind kind,
) => <String, Object?>{'editorKind': kind.name};

Map<String, Object?> createEditorSurfaceExtrasReady({
  required CreateEditorKind editorKind,
  required bool unifiedCreateEditorEnabled,
}) => <String, Object?>{
  'editorKind': editorKind.name,
  'flag': unifiedCreateEditorEnabled,
};

Map<String, Object?> createEditorSurfaceExtrasMediaBatch({
  required int count,
  required CreateEditorKind editorKind,
}) => <String, Object?>{'count': count, 'editorKind': editorKind.name};

Map<String, Object?> createEditorSurfaceExtrasVideoEdited({
  required bool muted,
  required int trimStartMs,
  required int trimEndMs,
}) => <String, Object?>{
  'muted': muted,
  'trimStartMs': trimStartMs,
  'trimEndMs': trimEndMs,
};

/// 与 [buildPostPublicationPayloadMap] 写入的 `contentType` 一致，供发布成功打点使用。
Map<String, Object?> createEditorSurfaceExtrasPublishSuccess(
  Map<String, Object?> payload,
) => <String, Object?>{'contentType': payload['contentType']};

ContentType _requiredPostType(Object? raw) => switch ('$raw'.trim()) {
  'image' => ContentType.image,
  'video' => ContentType.video,
  'micro' => ContentType.micro,
  'article' => ContentType.article,
  final value => throw ArgumentError.value(value, 'contentType', 'unsupported'),
};

ContentIdentity? _optionalPostIdentity(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'moment' => ContentIdentity.moment,
      'work' => ContentIdentity.work,
      final value => throw ArgumentError.value(
        value,
        'contentIdentity',
        'unsupported',
      ),
    };

Visibility? _optionalPostVisibility(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'public' => Visibility.public,
      'private' => Visibility.private,
      final value => throw ArgumentError.value(
        value,
        'visibility',
        'unsupported',
      ),
    };

AssistantUsePolicy? _optionalAssistantUsePolicy(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      final value => AssistantUsePolicy.fromWire(
        value,
        'SubmitContentPostPublicationCommand.assistantUsePolicy',
      ),
    };

PostSourceType? _optionalPostSourceType(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'original' => PostSourceType.original,
      'repost' => PostSourceType.repost,
      'quote' => PostSourceType.quote,
      final value => throw ArgumentError.value(
        value,
        'sourceType',
        'unsupported',
      ),
    };

String? _optionalPayloadText(Object? raw) {
  final value = raw?.toString().trim() ?? '';
  return value.isEmpty ? null : value;
}

List<String> _payloadStringList(Object? raw) {
  if (raw is! Iterable) return const <String>[];
  return raw
      .map((value) => value.toString().trim())
      .where((value) => value.isNotEmpty)
      .toSet()
      .toList(growable: false);
}

int? _optionalPayloadInt(Object? raw, String field) {
  if (raw == null) return null;
  if (raw is int) return raw;
  final parsed = int.tryParse('$raw');
  if (parsed == null) {
    throw ArgumentError.value(raw, field, 'must be an integer');
  }
  return parsed;
}

DateTime? _optionalPayloadTimestamp(Object? raw, String field) {
  if (raw == null) return null;
  if (raw is DateTime) return raw.toUtc();
  final parsed = DateTime.tryParse(raw.toString().trim());
  if (parsed == null) {
    throw ArgumentError.value(raw, field, 'must be an RFC3339 timestamp');
  }
  return parsed.toUtc();
}

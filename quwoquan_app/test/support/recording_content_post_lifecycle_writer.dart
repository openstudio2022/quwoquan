import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Canonical local-contract fixture for the typed Post lifecycle port.
final class RecordingContentPostLifecycleWriter
    implements ContentPostLifecycleCommandWriter {
  final List<CreateContentPostCommand> createCommands =
      <CreateContentPostCommand>[];
  final List<PublishContentPostCommand> publishCommands =
      <PublishContentPostCommand>[];

  Map<String, Object?>? get lastCreatePayload {
    if (createCommands.isEmpty) return null;
    final body = encodeCreateContentPostCommand(createCommands.last).body;
    if (body is! Map) {
      throw StateError('encoded create command body is not a map');
    }
    return body.map((key, value) => MapEntry(key.toString(), value));
  }

  @override
  Future<ContentPostLifecycleCommandResult> createPost(
    CreateContentPostCommand command,
  ) async {
    createCommands.add(command);
    return _result(
      ContentPostProjection(
        postId: 'post_test_1',
        contentType: command.contentType.name,
        contentIdentity: command.contentIdentity?.name,
        assistantUsePolicy: command.assistantUsePolicy?.name ?? 'inherit',
        authorId: 'test_author',
        authorDisplayName: command.authorDisplayNameSnapshot ?? 'Test',
        authorAvatarUrl: command.authorAvatarUrlSnapshot,
        title: command.title,
        body: command.body,
        summary: command.summary,
        coverUrl: command.coverUrl,
        imageUrls: command.mediaUrls,
        videoUrl: command.videoUrl,
        thumbnailUrl: command.thumbnailUrl,
        createdAt: DateTime.utc(2030),
      ),
      visibility: command.visibility?.name,
    );
  }

  @override
  Future<ContentPostLifecycleCommandResult> publishPost(
    PublishContentPostCommand command,
  ) async {
    publishCommands.add(command);
    final created = createCommands.last;
    return _result(
      ContentPostProjection(
        postId: command.postId,
        contentType: created.contentType.name,
        contentIdentity: command.contentIdentity?.name,
        assistantUsePolicy:
            command.assistantUsePolicy?.name ??
            created.assistantUsePolicy?.name ??
            'inherit',
        authorId: 'test_author',
        authorDisplayName: created.authorDisplayNameSnapshot ?? 'Test',
        authorAvatarUrl: created.authorAvatarUrlSnapshot,
        title: created.title,
        body: created.body,
        summary: created.summary,
        coverUrl: created.coverUrl,
        imageUrls: created.mediaUrls,
        videoUrl: created.videoUrl,
        thumbnailUrl: created.thumbnailUrl,
        createdAt: DateTime.utc(2030),
        publishedAt: DateTime.utc(2030),
      ),
      visibility: command.visibility?.name,
    );
  }

  ContentPostLifecycleCommandResult _result(
    ContentPostProjection projection, {
    String? visibility,
  }) => ContentPostLifecycleCommandResult(
    ContentPostDetailSlice(post: projection, visibility: visibility),
  );
}

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only Post lifecycle fixture。它实现与 production Remote 相同的 typed port。
final class AlphaContentPostLifecycleWriter
    implements ContentPostLifecycleCommandWriter {
  int _sequence = 0;
  final Map<String, ContentPostProjection> _drafts =
      <String, ContentPostProjection>{};

  @override
  Future<ContentPostLifecycleCommandResult> createPost(
    CreateContentPostCommand command,
  ) async {
    final postId = 'alpha_post_${++_sequence}';
    final projection = ContentPostProjection(
      postId: postId,
      contentType: command.contentType.name,
      contentIdentity: command.contentIdentity?.name,
      assistantUsePolicy: command.assistantUsePolicy?.name ?? 'inherit',
      authorId: 'alpha_persona',
      authorDisplayName: command.authorDisplayNameSnapshot ?? 'Alpha 用户',
      authorAvatarUrl: command.authorAvatarUrlSnapshot,
      title: command.title,
      body: command.body,
      summary: command.summary,
      coverUrl: command.coverUrl,
      imageUrls: command.mediaUrls,
      videoUrl: command.videoUrl,
      thumbnailUrl: command.thumbnailUrl,
      createdAt: DateTime.utc(2030),
    );
    _drafts[postId] = projection;
    return _result(projection, visibility: command.visibility?.name);
  }

  @override
  Future<ContentPostLifecycleCommandResult> publishPost(
    PublishContentPostCommand command,
  ) async {
    final draft = _drafts[command.postId];
    if (draft == null) throw StateError('alpha post draft not found');
    final published = ContentPostProjection(
      postId: draft.postId,
      contentType: draft.contentType,
      contentIdentity: command.contentIdentity?.name ?? draft.contentIdentity,
      assistantUsePolicy:
          command.assistantUsePolicy?.name ?? draft.assistantUsePolicy,
      authorId: draft.authorId,
      authorDisplayName: draft.authorDisplayName,
      authorAvatarUrl: draft.authorAvatarUrl,
      title: draft.title,
      body: draft.body,
      summary: draft.summary,
      coverUrl: draft.coverUrl,
      imageUrls: draft.imageUrls,
      videoUrl: draft.videoUrl,
      thumbnailUrl: draft.thumbnailUrl,
      createdAt: draft.createdAt,
      publishedAt: DateTime.utc(2030),
    );
    _drafts[command.postId] = published;
    return _result(published, visibility: command.visibility?.name);
  }

  ContentPostLifecycleCommandResult _result(
    ContentPostProjection projection, {
    String? visibility,
  }) => ContentPostLifecycleCommandResult(
    ContentPostDetailSlice(post: projection, visibility: visibility),
  );
}

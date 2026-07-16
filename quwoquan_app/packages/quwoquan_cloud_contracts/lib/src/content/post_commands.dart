import '../operation_request_payload.dart';
import 'post_reader_queries.dart';

enum ContentPostType { image, video, micro, article }

enum ContentPostIdentity { moment, work }

enum ContentPostVisibility { public, private }

enum ContentPostAssistantUsePolicy { inherit, exclude }

enum ContentPostSourceType { original, repost, quote }

/// Post create command contains business data only. Actor, surface, trace,
/// deadline and idempotency identity are supplied by
/// `CloudOperationInvocationContext`.
final class CreateContentPostCommand {
  CreateContentPostCommand({
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.body,
    this.summary,
    Iterable<ContentPostStructuredObject> semanticMentions = const [],
    Iterable<String> mediaUrls = const [],
    Iterable<ContentPostStructuredObject> mediaItems = const [],
    this.coverUrl,
    this.thumbnailUrl,
    this.articleMarkdown,
    this.articleMarkdownVersion,
    this.articleAssetManifest,
    this.articleRenderProfile,
    this.videoUrl,
    this.coverStrategy,
    this.coverFrameTimeMs,
    this.illustrationAssetId,
    this.location,
    this.locationName,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.assistantUsePolicy,
    this.sourcePostId,
    this.sourceType,
    this.deviceInfo,
    this.publishLocation,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    this.personaContextVersion,
  }) : semanticMentions = List<ContentPostStructuredObject>.unmodifiable(
         semanticMentions,
       ),
       mediaUrls = List<String>.unmodifiable(mediaUrls),
       mediaItems = List<ContentPostStructuredObject>.unmodifiable(mediaItems);

  final ContentPostType contentType;
  final ContentPostIdentity? contentIdentity;
  final String? title;
  final String? body;
  final String? summary;
  final List<ContentPostStructuredObject> semanticMentions;
  final List<String> mediaUrls;
  final List<ContentPostStructuredObject> mediaItems;
  final String? coverUrl;
  final String? thumbnailUrl;
  final String? articleMarkdown;
  final String? articleMarkdownVersion;
  final ContentPostStructuredObject? articleAssetManifest;
  final ContentPostStructuredObject? articleRenderProfile;
  final String? videoUrl;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final String? illustrationAssetId;
  final ContentPostStructuredObject? location;
  final String? locationName;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final ContentPostStructuredObject? primaryHomepageSnapshot;
  final ContentPostVisibility? visibility;
  final ContentPostAssistantUsePolicy? assistantUsePolicy;
  final String? sourcePostId;
  final ContentPostSourceType? sourceType;
  final ContentPostStructuredObject? deviceInfo;
  final ContentPostStructuredObject? publishLocation;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;
}

final class PublishContentPostCommand {
  PublishContentPostCommand({
    required String postId,
    this.contentIdentity,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.assistantUsePolicy,
  }) : postId = _requiredText(postId, 'postId');

  final String postId;
  final ContentPostIdentity? contentIdentity;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final ContentPostStructuredObject? primaryHomepageSnapshot;
  final ContentPostVisibility? visibility;
  final ContentPostAssistantUsePolicy? assistantUsePolicy;
}

/// Typed result shared by CreatePost and PublishPost. The decoder rejects a
/// malformed Post response through the same strict projection codec as GetPost.
final class ContentPostLifecycleCommandResult {
  const ContentPostLifecycleCommandResult(this.detail);

  final ContentPostDetailSlice detail;
  ContentPostProjection get post => detail.post;
}

/// Post 聚合生命周期的最小写入端口。
///
/// 调用方只能提交业务命令；operation id、path、actor、surface、deadline 与
/// idempotency 均由 Remote composition 注入，不能通过业务参数旁路 Runtime。
abstract interface class ContentPostLifecycleCommandWriter {
  Future<ContentPostLifecycleCommandResult> createPost(
    CreateContentPostCommand command,
  );

  Future<ContentPostLifecycleCommandResult> publishPost(
    PublishContentPostCommand command,
  );
}

CloudOperationRequestPayload encodeCreateContentPostCommand(
  CreateContentPostCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'contentType': command.contentType.name,
      if (command.contentIdentity != null)
        'contentIdentity': command.contentIdentity!.name,
      if (_optionalText(command.title) case final title?) 'title': title,
      if (_optionalText(command.body) case final body?) 'body': body,
      if (_optionalText(command.summary) case final summary?)
        'summary': summary,
      if (command.semanticMentions.isNotEmpty)
        'semanticMentions': command.semanticMentions
            .map(_encodeStructuredValue)
            .toList(growable: false),
      if (command.mediaUrls.isNotEmpty) 'mediaUrls': command.mediaUrls,
      if (command.mediaItems.isNotEmpty)
        'mediaItems': command.mediaItems
            .map(_encodeStructuredValue)
            .toList(growable: false),
      if (_optionalText(command.coverUrl) case final coverUrl?)
        'coverUrl': coverUrl,
      if (_optionalText(command.thumbnailUrl) case final thumbnailUrl?)
        'thumbnailUrl': thumbnailUrl,
      if (_optionalText(command.articleMarkdown) case final markdown?)
        'articleMarkdown': markdown,
      if (_optionalText(command.articleMarkdownVersion) case final version?)
        'articleMarkdownVersion': version,
      if (command.articleAssetManifest != null)
        'articleAssetManifest': _encodeStructuredValue(
          command.articleAssetManifest!,
        ),
      if (command.articleRenderProfile != null)
        'articleRenderProfile': _encodeStructuredValue(
          command.articleRenderProfile!,
        ),
      if (_optionalText(command.videoUrl) case final videoUrl?)
        'videoUrl': videoUrl,
      if (_optionalText(command.coverStrategy) case final strategy?)
        'coverStrategy': strategy,
      if (command.coverFrameTimeMs != null)
        'coverFrameTimeMs': command.coverFrameTimeMs,
      if (_optionalText(command.illustrationAssetId) case final assetId?)
        'illustrationAssetId': assetId,
      if (command.location != null)
        'location': _encodeStructuredValue(command.location!),
      if (_optionalText(command.locationName) case final locationName?)
        'locationName': locationName,
      if (_optionalText(command.primaryHomepageId) case final homepageId?)
        'primaryHomepageId': homepageId,
      if (_optionalText(command.primaryHomepageType) case final homepageType?)
        'primaryHomepageType': homepageType,
      if (command.primaryHomepageSnapshot != null)
        'primaryHomepageSnapshot': _encodeStructuredValue(
          command.primaryHomepageSnapshot!,
        ),
      if (command.visibility != null) 'visibility': command.visibility!.name,
      if (command.assistantUsePolicy != null)
        'assistantUsePolicy': command.assistantUsePolicy!.name,
      if (_optionalText(command.sourcePostId) case final sourcePostId?)
        'sourcePostId': sourcePostId,
      if (command.sourceType != null) 'sourceType': command.sourceType!.name,
      if (command.deviceInfo != null)
        'deviceInfo': _encodeStructuredValue(command.deviceInfo!),
      if (command.publishLocation != null)
        'publishLocation': _encodeStructuredValue(command.publishLocation!),
      if (_optionalText(command.authorDisplayNameSnapshot) case final name?)
        'authorDisplayNameSnapshot': name,
      if (_optionalText(command.authorAvatarUrlSnapshot) case final avatar?)
        'authorAvatarUrlSnapshot': avatar,
      if (command.personaContextVersion != null)
        'personaContextVersion': command.personaContextVersion,
    },
  );
}

CloudOperationRequestPayload encodePublishContentPostCommand(
  PublishContentPostCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'postId': command.postId},
    body: <String, Object?>{
      if (command.contentIdentity != null)
        'contentIdentity': command.contentIdentity!.name,
      if (_optionalText(command.primaryHomepageId) case final homepageId?)
        'primaryHomepageId': homepageId,
      if (_optionalText(command.primaryHomepageType) case final homepageType?)
        'primaryHomepageType': homepageType,
      if (command.primaryHomepageSnapshot != null)
        'primaryHomepageSnapshot': _encodeStructuredValue(
          command.primaryHomepageSnapshot!,
        ),
      if (command.visibility != null) 'visibility': command.visibility!.name,
      if (command.assistantUsePolicy != null)
        'assistantUsePolicy': command.assistantUsePolicy!.name,
    },
  );
}

ContentPostLifecycleCommandResult decodeContentPostLifecycleCommandResult(
  Object? response,
) {
  return ContentPostLifecycleCommandResult(
    decodeContentPostDetailSlice(response),
  );
}

Object? _encodeStructuredValue(ContentPostStructuredValue value) {
  return switch (value) {
    ContentPostStructuredObject(:final fields) => <String, Object?>{
      for (final entry in fields.entries)
        entry.key: _encodeStructuredValue(entry.value),
    },
    ContentPostStructuredArray(:final values) =>
      values.map(_encodeStructuredValue).toList(growable: false),
    ContentPostStructuredText(:final value) => value,
    ContentPostStructuredNumber(:final value) => value,
    ContentPostStructuredBoolean(:final value) => value,
    ContentPostStructuredNull() => null,
  };
}

String _requiredText(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return normalized;
}

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

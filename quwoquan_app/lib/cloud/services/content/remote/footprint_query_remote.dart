import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentFootprintInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// 我的足迹的正式远端适配器。
///
/// 通信完全由 GeneratedCloudOperationClient 执行；本层只处理纯合同到 UI DTO 的
/// 显式投影，保证已有足迹页面无需感知 transport。
final class RemoteFootprintRepository implements FootprintRepository {
  const RemoteFootprintRepository({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentFootprintInvocationContextFactory invocationContext;

  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  }) async {
    final response = await client.contentPostGetMyFootprint(
      ContentFootprintQuery(type: type, cursor: cursor, limit: limit),
      context: invocationContext(ContentRequestPageIds.getMyFootprint),
    );
    return CursorPage<FootprintEntry>(
      items: response.items.map(_toFootprintEntry).toList(growable: false),
      nextCursor: response.nextCursor,
    );
  }

  FootprintEntry _toFootprintEntry(ContentFootprintEntry entry) {
    return FootprintEntry(
      postId: entry.postId,
      action: entry.action,
      occurredAt: entry.occurredAt.toUtc().toIso8601String(),
      post: entry.post == null ? null : FootprintPostPreviewDto(entry.post!),
    );
  }
}

/// 足迹查询仅承诺内容预览字段，不能将其伪装成完整内容详情 projection。
final class FootprintPostPreviewDto extends PostBaseDto {
  FootprintPostPreviewDto(this._source);

  final ContentFootprintPostPreview _source;

  @override
  String get id => _source.postId;

  @override
  String get type => _source.contentType;

  @override
  String get identity => _source.contentIdentity ?? 'work';

  @override
  String get displayFormat {
    return switch (_source.contentType) {
      'image' => 'image',
      'video' => 'video',
      _ => 'note',
    };
  }

  @override
  String get authorId => _source.authorId ?? '';

  @override
  String get displayName => _source.authorDisplayName ?? '';

  @override
  String get avatarUrl => _source.authorAvatarUrl ?? '';

  @override
  String? get authorBackgroundUrl => _source.authorBackgroundUrl;

  @override
  String get assistantUsePolicy => 'inherit';

  @override
  int get likeCount => 0;

  @override
  int get commentCount => 0;

  @override
  int get shareCount => 0;

  @override
  DateTime get createdAt =>
      _source.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

  @override
  String get title => _source.title ?? '';

  @override
  String? get body => _source.body;

  @override
  List<String> get imageUrls => _source.imageUrls;

  @override
  String? get coverUrl => _source.coverUrl;

  @override
  String? get videoUrl => _source.videoUrl;

  @override
  String? get thumbnailUrl => _source.thumbnailUrl;

  @override
  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'postId': id,
      'contentType': type,
      'contentIdentity': identity,
      'title': title,
      'body': body,
      'authorId': authorId,
      'authorDisplayName': displayName,
      'authorAvatarUrl': avatarUrl,
      'authorBackgroundUrl': authorBackgroundUrl,
      'coverUrl': coverUrl,
      'imageUrls': imageUrls,
      'videoUrl': videoUrl,
      'thumbnailUrl': thumbnailUrl,
      'createdAt': createdAt.toIso8601String(),
    };
  }
}

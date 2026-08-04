import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
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
      post: entry.post == null
          ? null
          : ContentPostViewData.fromWire(entry.post!),
    );
  }
}

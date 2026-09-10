import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 与 Remote 共用 typed 详情、作者作品 ports 和 generated decoder；没有网络依赖。
final class BundledContentPostReader
    implements ContentPostDetailReader, ContentAuthorPostsReader {
  BundledContentPostReader({required this.loadBundle});
  final Future<OfflineContentBundle> Function() loadBundle;
  Future<OfflineContentBundle>? _bundle;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final readBudgetDeadline = DateTime.now().add(const Duration(seconds: 6));
    final effectiveDeadline =
        deadlineAt == null || deadlineAt.isAfter(readBudgetDeadline)
        ? readBudgetDeadline
        : deadlineAt;
    final bundle = await runCloudOperationPrerequisite(
      () => _bundle ??= loadBundle().catchError((Object error) {
        _bundle = null;
        throw error;
      }),
      cancellation: cancellation,
      deadlineAt: effectiveDeadline,
    );
    final rows = bundle
        .rows('posts')
        .where(
          (row) =>
              (row['projection']! as Map<String, Object?>)['postId'] == postId,
        );
    if (rows.length != 1) {
      throw const OfflineContentFailure('bundle_post_not_found');
    }
    final detail = ContentPostDetailSlice.fromWire(
      rows.single['detail']! as Map<String, Object?>,
    );
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: effectiveDeadline,
    );
    return ContentPostDetailPayload.fromWire(detail);
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) async {
    if (userId.trim().isEmpty ||
        userId.trim() == 'me' ||
        (visibility != null && visibility != 'public')) {
      throw contentCapabilityUnavailable('private_author_posts');
    }
    if (limit < 1 || limit > 100) {
      throw const OfflineContentFailure('bundle_query_limit_invalid');
    }
    final bundle = await (_bundle ??= loadBundle().catchError((Object error) {
      _bundle = null;
      throw error;
    })).timeout(const Duration(seconds: 6));
    final rows = bundle
        .rows('posts')
        .map(
          (row) => ContentPostProjection.fromWire(
            row['projection']! as Map<String, Object?>,
          ),
        )
        .where(
          (post) =>
              post.authorId == userId.trim() &&
              (identity == null || post.contentIdentity == identity) &&
              (type == null || post.contentType == type),
        )
        .toList(growable: false);
    final queryDigest = sha256
        .convert(
          utf8.encode(
            jsonEncode([
              bundle.digest,
              'author_posts',
              userId.trim(),
              identity,
              type,
              visibility,
              limit,
            ]),
          ),
        )
        .toString();
    var offset = 0;
    if (cursor != null && cursor.isNotEmpty) {
      final parts = cursor.split(':');
      final parsed = parts.length == 2 ? int.tryParse(parts.last) : null;
      if (parts.first != queryDigest ||
          parsed == null ||
          '$parsed' != parts.last ||
          parsed < 0 ||
          parsed > rows.length) {
        throw const OfflineContentFailure('bundle_query_cursor_invalid');
      }
      offset = parsed;
    }
    final items = rows
        .skip(offset)
        .take(limit)
        .map(const ContentPostProjectionMapper().toDto)
        .toList(growable: false);
    return CursorPage<ContentPostViewData>(
      items: items,
      nextCursor: offset + items.length < rows.length
          ? '$queryDigest:${offset + items.length}'
          : null,
    );
  }
}

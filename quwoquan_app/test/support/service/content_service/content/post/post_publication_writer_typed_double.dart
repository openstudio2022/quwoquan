import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only 原子发布 fixture，与 production Remote 共享同一 typed port。
final class InMemoryContentPostPublicationWriter
    implements ContentPostPublicationWriter {
  int _sequence = 0;
  final Map<String, PostPublicationReceipt> _receiptsByIntent =
      <String, PostPublicationReceipt>{};

  @override
  Future<PostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    final existing = _receiptsByIntent[command.publishIntentId];
    if (existing != null) {
      if (existing.localDraftId != command.localDraftId) {
        throw StateError('publish intent belongs to another local draft');
      }
      return existing;
    }
    final receipt = PostPublicationReceipt(
      publishIntentId: command.publishIntentId,
      localDraftId: command.localDraftId,
      postId: 'fixture_post_${++_sequence}',
      state: 'published',
      committedVersion: 1,
      acceptedAt: DateTime.utc(2030),
    );
    _receiptsByIntent[command.publishIntentId] = receipt;
    return receipt;
  }
}
